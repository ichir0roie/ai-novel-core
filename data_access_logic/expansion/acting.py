"""人物モード(`ActCharacter`)の db だけの処理。段(`expansion/steps.py`)が呼ぶ。

人物モードは書き手 `ai_append` で書くので、足すことと、`end` で終わりを付けることだけをする(`db/guard.py`)。
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from data_access_logic import constants
from data_access_logic.character.knowledge import _related_ids, appearance_of, knowledge_of
from data_access_logic.character.motivations import apply_changes, motivations_at
from data_access_logic.character.moves import allowed_moves, update_locations
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.record import CharacterMotivationRecord
from data_access_logic.entrypoint import record_of
from data_access_logic.event import progress
from data_access_logic.event.plan import _current_location_id
from data_access_logic.event.record import EventRecord
from data_access_logic.event.summary import events_of
from data_access_logic.expansion import budget
from data_access_logic.expansion.act_models import (
    ActFrameForm, ActorBrief, ActorPick, ActorSerialized, ActSaved, ActSaveForm, ArcEvent, DialogueBrief, DialogueBriefForm,
    DialogueSerialized, ImpactFrame, InviteForm, MotivationLine, Motives, NarratedEpisode, Narration, NarratorBrief,
    NarratorSerialized, NewCharacterLink, OpenArc, ParentArc, ParticipantMotivations, PresentPerson,
)
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.query import common_query, expansion_query, world_creation_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import (
    CHARACTER_KIND_PERSON, Character, CharacterLocation, CharacterRelation, Episode, EpisodeCharacter, Event, EventCharacter,
    IdeaHistory, IdeaHistoryKnower, Location,
)
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def _people_here(s: Session, location_id: int, time: Stamp) -> list[Character]:
    """その場所・時刻に居合わせて手の空いた人物・対象。出来事の生成(`_present_characters`)と違って主要人物も含める。
    主要人物は自分からは動かないが、目に入り、巻きこまれる側にはなる(動かされにくさは影響の枠で守る)。"""
    busy_ids = set(s.scalars(world_creation_query.busy_character_ids_select(time)).all())
    characters = s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(Character.locations.any(CharacterLocation.location_id == location_id))
        .order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in busy_ids and _current_location_id(character, time) == location_id]


def _partners(s: Session, partner_ids: list[int], exclude_id: int, time: Stamp) -> list[Character]:
    """作者が居合わせさせた人物のうち、その時刻に生きている人物(渡した順)。"""
    partners = [s.get_one(Character, id_) for id_ in dict.fromkeys(partner_ids) if id_ != exclude_id]
    return [partner for partner in partners
            if (partner.start is None or partner.start <= time) and (partner.end is None or partner.end > time)]


def _present(s: Session, pick: ActorPick, exclude_id: int, time: Stamp) -> list[Character]:
    """目の前にいる人物。作者が居合わせさせた人物を先に、同じ場所に居合わせて手の空いた人物を続ける(上限まで)。"""
    partners = _partners(s, pick.partner_ids, exclude_id, time)
    seen_ids = {partner.id for partner in partners}
    here = [other for other in _people_here(s, pick.location_id, time) if other.id != exclude_id and other.id not in seen_ids]
    return [*partners, *here][:constants.ACT_PRESENT_LIMIT]


def _weight(character: Character, time: Stamp) -> int:
    return constants.ACTOR_WEIGHTS.get(parameters_at(character, time).proactivity or "並", 0)


def _choose_actor(s: Session, rng: random.Random, time: Stamp, exclude_ids: list[int]) -> Character:
    """その時刻に生きて居場所があり、気力と手数の足りる、人物のサブキャラクターから、行動力の重みで引く。"""
    candidates = [character for character in s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(world_creation_query.character_active_condition(), Character.kind == CHARACTER_KIND_PERSON)
        .order_by(Character.id)).all()
        if character.id not in exclude_ids and _current_location_id(character, time) is not None
        and budget.can_act(s, character, time)]
    weights = [_weight(character, time) for character in candidates]
    if not candidates or not any(weights):
        raise ValueError(f"{time} に動ける(生きて居場所があり、行動力が無でなく、気力と手数の残る)サブキャラクターがいない")
    return rng.choices(candidates, weights=weights)[0]


def _choose_from_cast(s: Session, rng: random.Random, episode: Episode, exclude_ids: list[int]) -> Character:
    """話に登場した(名前だけでない)人物から、行動力の重みで引く。作者の頼み(最新の話の登場人物を動かす)なので、主要人物も含める。"""
    time = expansion_query.episode_time(episode)
    candidates = [character for character in s.scalars(
        select(Character).join(EpisodeCharacter, EpisodeCharacter.character_id == Character.id)
        .where(EpisodeCharacter.episode_id == episode.id, EpisodeCharacter.mentioned.is_(False),
               Character.kind == CHARACTER_KIND_PERSON)
        .order_by(Character.id)).all()
        if character.id not in exclude_ids and (character.end is None or character.end > time)]
    weights = [_weight(character, time) for character in candidates]
    if not candidates or not any(weights):
        raise ValueError(f"話「{episode.title}」(id={episode.id})の登場人物に、まだ動いていない行動力のある人物がいない")
    return rng.choices(candidates, weights=weights)[0]


def _next_time(s: Session, rng: random.Random, character: Character) -> Stamp:
    """人物が最後に出た時刻(`expansion_query.last_appearance`)から、`constants.ACT_INTERVAL_DAYS` の範囲で日を空けた時刻。
    出たことが無ければ世界の最新の時刻。"""
    last = expansion_query.last_appearance(s, character.id)
    if last is not None:
        return last.plus_days(rng.randint(*constants.ACT_INTERVAL_DAYS))
    latest = s.scalar(common_query.latest_time_select())
    if latest is None:
        raise ValueError("世界にまだ出来事が無いので、動く時刻を決められない。time を渡す")
    return latest


def _ready(s: Session, character: Character, at: Stamp, fixed: bool) -> Stamp:
    """`at` に打てなければ、気力と手数の戻る日まで待たせる。時刻を名指しされたら待たせずに止める。"""
    ready = budget.ready_time(s, character, at)
    if ready is None:
        raise ValueError(f"{character.name}(id={character.id})は行動力が無いので自分からは動かない")
    if fixed and ready != at:
        raise ValueError(
            f"{character.name}(id={character.id})は {at} には気力か手数が足りない"
            f"(気力 {budget.energy_at(s, character, at):.1f}・{constants.ACT_WINDOW_DAYS}日の手数 "
            f"{budget.acts_in_window(s, character.id, at)})。{ready} からなら動ける")
    return ready


def pick_actor(
    s: Session, character_id: int | None, time: Stamp | None, seed: int | None, exclude_ids: list[int],
    cast_of: int | None = None, parent_event_id: int | None = None, partner_ids: list[int] | None = None,
) -> ActorPick:
    """人物も時刻も渡されなければ、本文のある最新の話(`cast_of` を渡せば、その人物が登場した最新の話)の登場人物から引き、
    その話より後(`_next_time`)に動かす。本文のある話が無ければ、世界の最新の時刻のサブキャラクターから引く。
    親の出来事を渡したら、人物を渡させ、時刻を親の期間に収める(`_in_parent`)。"""
    rng = random.Random(seed)
    if parent_event_id is not None:
        if character_id is None:
            raise ValueError("親の出来事を渡すときは、動く人物を渡す")
        return _in_parent(s, rng, character_id, time, parent_event_id, partner_ids or [])
    episode = None
    if character_id is None and time is None:
        episode = ((cast_of is not None and expansion_query.latest_written_episode(s, cast_of))
                   or expansion_query.latest_written_episode(s))
    if character_id is not None:
        character = common_query.get_row(s, Character, character_id)
        at = _ready(s, character, time or _next_time(s, rng, character), time is not None)
    elif episode is not None:
        character = _choose_from_cast(s, rng, episode, exclude_ids)
        at = _ready(s, character, _next_time(s, rng, character), False)
    else:
        latest = time or s.scalar(common_query.latest_time_select())
        if latest is None:
            raise ValueError("世界にまだ出来事が無いので、動く時刻を決められない。time を渡す")
        character = _choose_actor(s, rng, latest, exclude_ids)
        at = time or _ready(s, character, _next_time(s, rng, character), False)
    if character.end is not None and character.end <= at:
        raise ValueError(f"{character.name}(id={character.id})は {at} にはもういない(没年 {character.end})")
    return _pick(s, character, at)


def _pick(s: Session, character: Character, at: Stamp, parent_event_id: int | None = None,
          partner_ids: list[int] | None = None) -> ActorPick:
    location_id = _current_location_id(character, at)
    if location_id is None:
        raise ValueError(f"{character.name}(id={character.id})の {at} の居場所が分からない")
    return ActorPick(character_id=character.id, name=character.name, time=at, location_id=location_id,
                     energy=round(budget.energy_at(s, character, at), 1), influence=budget.influence_of(character, at),
                     parent_event_id=parent_event_id, partner_ids=partner_ids or [])


def _in_parent(s: Session, rng: random.Random, character_id: int, time: Stamp | None, parent_event_id: int,
               partner_ids: list[int]) -> ActorPick:
    """作者が置いた親の出来事の期間(終わりが空なら始まりから先)で動かす。時刻を省けば、人物が最後に出た時刻から日を空けた時刻を
    親の始まりより後に寄せ、気力と手数の戻るまで待たせる。期間を出るなら止める。"""
    parent = common_query.get_row(s, Event, parent_event_id)
    character = common_query.get_row(s, Character, character_id)
    if time is None:
        at = _ready(s, character, max(_next_time(s, rng, character), parent.time), False)
    else:
        at = _ready(s, character, time, True)
    if at < parent.time or (parent.end is not None and at >= parent.end):
        raise ValueError(f"{character.name}(id={character.id})が動ける {at} は、親の出来事「{parent.name}」(id={parent.id})の"
                         f"期間({parent.time}〜{parent.end or ''})の外")
    if character.end is not None and character.end <= at:
        raise ValueError(f"{character.name}(id={character.id})は {at} にはもういない(没年 {character.end})")
    for partner_id in partner_ids:
        common_query.get_row(s, Character, partner_id)
    alive_ids = {partner.id for partner in _partners(s, partner_ids, character.id, at)}
    absent = [partner_id for partner_id in dict.fromkeys(partner_ids)
              if partner_id != character.id and partner_id not in alive_ids]
    if absent:
        raise ValueError(f"居合わせさせる人物 id={absent} は {at} に生きていない")
    return _pick(s, character, at, parent.id, partner_ids)


def _past_events_select(character_id: int, time: Stamp) -> Select[Event]:
    return common_query.events_of_character_select(character_id, until=time, limit=constants.RECENT_EVENT_LIMIT)


def _later_events_select(character_id: int, location_id: int | None, time: Stamp) -> Select[Event]:
    return common_query.events_after_select(location_id, [character_id], time, limit=constants.LATER_EVENT_LIMIT)


def motive_targets(s: Session, character_ids: list[int], time: Stamp) -> SummaryTargets:
    """人物の目に要約で渡す、前後の出来事。"""
    event_ids = []
    for character_id in character_ids:
        location_id = _current_location_id(s.get_one(Character, character_id), time)
        for query in (_past_events_select(character_id, time), _later_events_select(character_id, location_id, time)):
            event_ids += [event.id for event in s.scalars(query).all()]
    return SummaryTargets(event_ids=list(dict.fromkeys(event_ids)))


def motives_of(s: Session, character: Character, time: Stamp) -> Motives:
    """本人のモチベーションと前後の出来事。要約は揃えてある前提でそのまま読む。"""
    location_id = _current_location_id(character, time)
    return Motives(
        motivations=[MotivationLine.model_validate(row) for row in motivations_at(s, character.id, time)],
        past_events=events_of(s, _past_events_select(character.id, time)),
        later_events=events_of(s, _later_events_select(character.id, location_id, time)),
    )


def participant_motivations(s: Session, character_ids: list[int], time: Stamp) -> list[ParticipantMotivations]:
    """裁く段に渡す、居合わせる人物ごとのモチベーション(並びは渡した順。動いた人物を先に渡す)。"""
    people = []
    for character_id in dict.fromkeys(character_ids):
        character = s.get_one(Character, character_id)
        people.append(ParticipantMotivations(
            character_id=character.id, name=character.name,
            motivations=[MotivationLine.model_validate(row) for row in motivations_at(s, character.id, time)]))
    return people


def open_arcs(s: Session, character_id: int) -> list[OpenArc]:
    return [OpenArc(id=event.id, name=event.name, text=event.text)
            for event in s.scalars(expansion_query.open_arcs_select(character_id)).all()]


def _distance_days(episode: Episode, time: Stamp) -> int:
    assert episode.start is not None
    end = episode.end or episode.start
    if episode.start <= time <= end:
        return 0
    return min(abs(time.days_until(episode.start)), abs(time.days_until(end)))


def related_episodes(s: Session, characters: list[Character], time: Stamp) -> list[NarratedEpisode]:
    """一手の時刻の前後 `ACT_NARRATOR_EPISODE_DAYS` 日にかかる、プロットつきの話のうち、`characters` の誰かが登場人物に結ばれているか、
    プロットに名前の出る話。近い話から上限まで取り、時刻の順に返す。作品は問わない(人物が出る話はどの章のプロットにも逆らわせない)。"""
    since = time.plus_days(-constants.ACT_NARRATOR_EPISODE_DAYS)
    until = time.plus_days(constants.ACT_NARRATOR_EPISODE_DAYS)
    ids = {character.id for character in characters}
    names = [character.name for character in characters if character.name]
    episodes = [episode for episode in s.scalars(
        select(Episode).options(selectinload(Episode.episode_characters))
        .where(Episode.start.is_not(None), Episode.plot_text != "", Episode.start <= until,
               func.coalesce(Episode.end, Episode.start) >= since)
        .order_by(Episode.start, Episode.id).execution_options(populate_existing=True)).all()
        if any(link.character_id in ids and not link.mentioned for link in episode.episode_characters)
        or any(name in episode.plot_text for name in names)]
    nearest = sorted(episodes, key=lambda episode: (_distance_days(episode, time), episode.id))
    chosen = sorted(nearest[:constants.ACT_NARRATOR_EPISODE_LIMIT], key=lambda episode: (episode.start, episode.id))
    return [NarratedEpisode(id=episode.id, title=episode.title, start=episode.start, end=episode.end,
                            plot_text=episode.plot_text, written=bool(episode.main_text.strip())) for episode in chosen]


def _arc_event(event: Event) -> ArcEvent:
    return ArcEvent(id=event.id, name=event.name, time=event.time, end=event.end, text=event.text)


def parent_arc(s: Session, parent_event_id: int, time: Stamp) -> ParentArc:
    """親の出来事と、その先祖(一番上まで)と、親の子のうち一手の時刻の前・後に近いものを上限まで。"""
    chain: list[ArcEvent] = []
    event: Event | None = common_query.get_row(s, Event, parent_event_id)
    while event is not None and len(chain) < constants.ACT_ARC_DEPTH_LIMIT:
        chain.insert(0, _arc_event(event))
        event = None if event.parent_event_id is None else s.get(Event, event.parent_event_id)
    children = s.scalars(select(Event).where(Event.parent_event_id == parent_event_id)
                         .order_by(Event.time, Event.id)).all()
    limit = constants.ACT_ARC_SIBLING_LIMIT
    return ParentArc(chain=chain, before=[_arc_event(child) for child in children if child.time < time][-limit:],
                     after=[_arc_event(child) for child in children if child.time >= time][:limit])


def narrator_brief(s: Session, pick: ActorPick, nudge: str | None) -> NarratorBrief:
    """語り部の材料。作者が置いた親の出来事の筋と、動く人物と居合わせる人物が出る前後の話のプロットと、場所・時刻・居合わせる人物・
    近ごろの出来事。人物の来歴・筋書きは読まない(語り部が動かすのは人物の外のことだけ)。"""
    character = s.get_one(Character, pick.character_id)
    time = Stamp.parse(pick.time)
    assert time is not None
    present = _present(s, pick, character.id, time)
    episodes = related_episodes(s, [character, *present], time)
    parent = None if pick.parent_event_id is None else parent_arc(s, pick.parent_event_id, time)
    if not episodes and parent is None:
        return NarratorBrief(prompt={}, episodes=[])
    recent = s.scalars(common_query.events_of_location_select(
        pick.location_id, until=time, limit=constants.RECENT_EVENT_LIMIT)).all()
    prompt = NarratorSerialized(
        time=time, location_name=s.get_one(Location, pick.location_id).name, actor_name=character.name,
        present_names=[other.name for other in present], recent_events=[event.name for event in recent],
        arcs=open_arcs(s, character.id), episodes=episodes, parent=parent, nudge=nudge,
    ).model_dump()
    return NarratorBrief(prompt=prompt, episodes=episodes, parent=parent)


def actor_brief(s: Session, pick: ActorPick, seeds: list[str], nudge: str | None,
                narration: Narration | None) -> ActorBrief:
    """人物の目で見た材料。知ることのできるデータ(知る相手で絞った来歴・関係・アイデア)と、目の前の様子と、
    語り部が目の前で起こしたこと・求めることだけ(語り部の動機と前後の話のプロットは渡さない)。"""
    character = s.get_one(Character, pick.character_id)
    time = Stamp.parse(pick.time)
    assert time is not None
    present = _present(s, pick, character.id, time)
    known_ids = set(_related_ids(s, character, time))
    recent = s.scalars(common_query.events_of_location_select(
        pick.location_id, until=time, limit=constants.RECENT_EVENT_LIMIT)).all()
    arcs = open_arcs(s, character.id)
    told = None if narration is None else narration.narration
    asked = None if narration is None else narration.request
    # 人物が知っているアイデアのうち、目の前の出来事・企て・方向づけ・語り部の語りと要求に名前の出るものを渡す
    mentioned = "\n".join([*(event.name for event in recent), *(arc.name for arc in arcs), nudge or "", told or "",
                           asked or ""])
    prompt = ActorSerialized(
        time=time, location_name=s.get_one(Location, pick.location_id).name,
        knowledge=knowledge_of(s, character.id, time, mentioned, None, None, with_now=False),
        motives=motives_of(s, character, time),
        present=[PresentPerson(character_id=other.id, name=other.name if other.id in known_ids else None,
                               looks=appearance_of(s, other, time)) for other in present],
        recent_events=[event.name for event in recent], arcs=arcs, seeds=seeds, nudge=nudge,
        narration=told, request=asked,
    ).model_dump()
    return ActorBrief(prompt=prompt, present_ids=[other.id for other in present], arcs=arcs)


def invitable(s: Session, form: InviteForm) -> list[int]:
    """狙う段が巻きこみたいと挙げた相手のうち、目の前にいて、動いた人物が名前を知り、気力の残る人物(挙げた順、上限まで)。"""
    actor = s.get_one(Character, form.actor_id)
    present_ids = {other.id for other in [*_partners(s, form.partner_ids, actor.id, form.time),
                                          *_people_here(s, form.location_id, form.time)]}
    known_ids = set(_related_ids(s, actor, form.time))
    chosen = []
    for character_id in dict.fromkeys(form.candidate_ids):
        if (character_id == actor.id or character_id in form.exclude_ids or character_id not in present_ids
                or character_id not in known_ids):
            continue
        if budget.can_be_involved(s, s.get_one(Character, character_id), form.time):
            chosen.append(character_id)
    return chosen[:constants.ACT_INVITE_LIMIT]


def dialogue_brief(s: Session, form: DialogueBriefForm) -> DialogueBrief:
    """対話の手番の材料。人物役(`ReadKnowledge`)と同じく、その時刻に知ることのできるデータと、目の前にいる人物だけ。"""
    character = s.get_one(Character, form.character_id)
    others = [s.get_one(Character, id_) for id_ in form.participant_ids if id_ != character.id]
    seen_ids = {other.id for other in others}
    others += [other for other in _people_here(s, form.location_id, form.time)
               if other.id != character.id and other.id not in seen_ids]
    others = others[:constants.ACT_PRESENT_LIMIT]
    known_ids = _related_ids(s, character, form.time)
    prompt = DialogueSerialized(
        time=form.time, location_name=s.get_one(Location, form.location_id).name,
        knowledge=knowledge_of(s, character.id, form.time, form.mentioned, None, None, with_now=False),
        motives=motives_of(s, character, form.time),
        present=[PresentPerson(character_id=other.id, name=other.name if other.id in known_ids else None,
                               looks=appearance_of(s, other, form.time)) for other in others],
        narration=form.narration,
    ).model_dump()
    return DialogueBrief(character_id=character.id, name=character.name, prompt=prompt, known_ids=known_ids)


def act_frame(s: Session, form: ActFrameForm) -> ImpactFrame:
    actor = s.get_one(Character, form.actor_id)
    participants = [s.get_one(Character, id_) for id_ in dict.fromkeys(form.participant_ids)]
    return budget.frame(s, actor, participants, form.time, form.roll)


def _arc_id(s: Session, form: ActSaveForm) -> int | None:
    """続ける企てか、新しく始める企て(親の出来事。終わりは空のまま)。"""
    intent = form.intent
    if intent.arc_id is not None and any(arc.id == intent.arc_id for arc in open_arcs(s, form.actor_id)):
        return intent.arc_id
    if not (intent.new_arc_name or "").strip():
        return None
    arc = Event(name=intent.new_arc_name, text=intent.aim, time=form.time, location_id=form.location_id,
                event_characters=[EventCharacter(character_id=form.actor_id)])
    s.add(arc)
    s.flush()
    return arc.id


def _add_ideas(s: Session, form: ActSaveForm, participant_ids: set[int]) -> list[int]:
    """一手で生まれた・広まった事柄を、アイデアと照らして(無ければ候補として足し)、この場所・時刻からの呼び名の行を、知った人物を
    知る相手にして足す。"""
    idea_ids = []
    for draft in form.outcome.ideas[:constants.ACT_NEW_IDEA_LIMIT]:
        context = resolve_ideas(s, [IdeaDraft(keyword=draft.keyword, kind=draft.kind, description=draft.description,
                                              start=form.time)], form.location_id, form.time)
        found = [*context.candidates, *context.hits]
        if not found:
            logger.warning(f"事柄「{draft.keyword}」をアイデアにできなかった(人名・地名と重なるなど)")
            continue
        knower_ids = [knower_id for knower_id in dict.fromkeys(draft.knower_ids) if knower_id in participant_ids]
        s.add(IdeaHistory(idea_id=found[0].id, location_id=form.location_id, start=form.time,
                          name=draft.called or draft.keyword, detail=draft.detail,
                          knowers=[IdeaHistoryKnower(knower_id=knower_id, start=form.time) for knower_id in knower_ids]))
        idea_ids.append(found[0].id)
    s.flush()
    return idea_ids


def save_act(s: Session, form: ActSaveForm) -> ActSaved:
    """裁いた結果を足す。出来事と当事者の来歴・場所の消滅と新設は出来事の生成(`progress.save_progress`)と同じに書き、
    企ての親に結び、事柄の呼び名と、居場所の移動(今の行に end を入れて移動先の行を足す)を足す。"""
    participant_ids = [form.actor_id, *(id_ for id_ in form.participant_ids if id_ != form.actor_id)]
    characters = [s.get_one(Character, id_) for id_ in participant_ids]
    # 作者が親を置いた手は、企てに結ばず親の子にする(出来事の親は一つなので)
    arc_id = None if form.parent_event_id is not None else _arc_id(s, form)
    record = progress.save_progress(s, form.location_id, characters, form.time, form.destinations, form.outcome)
    if form.actor_id not in [link.character_id for link in record.event_characters]:
        record.event_characters.append(EventCharacter(character_id=form.actor_id))
    record.parent_event_id = form.parent_event_id if form.parent_event_id is not None else arc_id
    s.flush()
    idea_ids = _add_ideas(s, form, set(participant_ids))
    moves = allowed_moves(form.outcome.character_moves, participant_ids,
                          [destination.id for destination in form.destinations])
    if moves:
        update_locations(s, moves, form.time)
    motivations = apply_changes(s, form.outcome.motivation_changes, participant_ids, form.time)
    if arc_id is not None and form.outcome.arc_closed:
        arc = s.get_one(Event, arc_id)
        if arc.end is None:
            arc.end = form.time
            s.flush()
    return ActSaved(event=record_of(s, EventRecord, record), arc_id=arc_id, idea_ids=idea_ids, moves=moves,
                    motivations=[CharacterMotivationRecord.model_validate(row) for row in motivations])


def link_new_character(s: Session, link: NewCharacterLink) -> None:
    """一手で現れた人物・対象を、出来事の当事者に入れ、動いた人物との関係を足す。"""
    s.add(EventCharacter(event_id=link.event_id, character_id=link.character_id))
    s.add(CharacterRelation(character_1_id=link.actor_id, character_2_id=link.character_id, relation=link.relation,
                            text="", start=link.time))
    s.flush()
