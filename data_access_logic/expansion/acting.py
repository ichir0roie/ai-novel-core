"""人物モード(`ActCharacter`)の db だけの処理。段(`expansion/steps.py`)が呼ぶ。

人物モードは書き手 `ai_append` で書くので、足すことと、`end` で終わりを付けることだけをする(`db/guard.py`)。
"""
from __future__ import annotations

import logging
import random

from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character.knowledge import _related_ids, appearance_of, knowledge_of
from data_access_logic.character.moves import allowed_moves, update_locations
from data_access_logic.character.parameters import parameters_at
from data_access_logic.entrypoint import record_of
from data_access_logic.event import progress
from data_access_logic.event.plan import _current_location_id, _present_characters
from data_access_logic.event.record import EventRecord
from data_access_logic.expansion.act_models import (
    ActorBrief, ActorPick, ActorSerialized, ActSaved, ActSaveForm, NewCharacterLink, OpenArc, PresentPerson,
)
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.query import common_query, expansion_query, world_creation_query
from db.schema import (
    CHARACTER_KIND_PERSON, Character, CharacterRelation, Event, EventCharacter, IdeaHistory, IdeaHistoryKnower, Location,
)
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def _weight(character: Character, time: Stamp) -> int:
    return constants.ACTOR_WEIGHTS.get(parameters_at(character, time).proactivity or "並", 0)


def _choose_actor(s: Session, rng: random.Random, time: Stamp) -> Character:
    """その時刻に生きて居場所のある、人物のサブキャラクターから、行動力の重みで引く。"""
    candidates = [character for character in s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(world_creation_query.character_active_condition(), Character.kind == CHARACTER_KIND_PERSON)
        .order_by(Character.id)).all() if _current_location_id(character, time) is not None]
    weights = [_weight(character, time) for character in candidates]
    if not candidates or not any(weights):
        raise ValueError(f"{time} に動ける(生きて居場所があり、行動力が無でない)サブキャラクターがいない")
    return rng.choices(candidates, weights=weights)[0]


def _next_time(s: Session, rng: random.Random, character: Character) -> Stamp:
    """人物が最後に出た出来事・話から、`constants.ACT_INTERVAL_DAYS` の範囲で日を空けた時刻。出たことが無ければ世界の最新の時刻。"""
    last = expansion_query.last_appearance(s, character.id)
    if last is not None:
        return last.plus_days(rng.randint(*constants.ACT_INTERVAL_DAYS))
    latest = s.scalar(common_query.latest_time_select())
    if latest is None:
        raise ValueError("世界にまだ出来事が無いので、動く時刻を決められない。time を渡す")
    return latest


def pick_actor(s: Session, character_id: int | None, time: Stamp | None, seed: int | None) -> ActorPick:
    rng = random.Random(seed)
    if character_id is not None:
        character = common_query.get_row(s, Character, character_id)
        at = time or _next_time(s, rng, character)
    else:
        latest = time or s.scalar(common_query.latest_time_select())
        if latest is None:
            raise ValueError("世界にまだ出来事が無いので、動く時刻を決められない。time を渡す")
        character = _choose_actor(s, rng, latest)
        at = time or _next_time(s, rng, character)
    if character.end is not None and character.end <= at:
        raise ValueError(f"{character.name}(id={character.id})は {at} にはもういない(没年 {character.end})")
    location_id = _current_location_id(character, at)
    if location_id is None:
        raise ValueError(f"{character.name}(id={character.id})の {at} の居場所が分からない")
    return ActorPick(character_id=character.id, name=character.name, time=at, location_id=location_id)


def open_arcs(s: Session, character_id: int) -> list[OpenArc]:
    return [OpenArc(id=event.id, name=event.name, text=event.text)
            for event in s.scalars(expansion_query.open_arcs_select(character_id)).all()]


def actor_brief(s: Session, pick: ActorPick, seeds: list[str], nudge: str | None) -> ActorBrief:
    """人物の目で見た材料。知ることのできるデータ(知る相手で絞った来歴・関係・アイデア)と、目の前の様子だけ。"""
    character = s.get_one(Character, pick.character_id)
    time = Stamp.parse(pick.time)
    assert time is not None
    present = [other for other in _present_characters(s, pick.location_id, time)
               if other.id != character.id][:constants.ACT_PRESENT_LIMIT]
    known_ids = set(_related_ids(s, character, time))
    recent = s.scalars(common_query.events_of_location_select(
        pick.location_id, until=time, limit=constants.RECENT_EVENT_LIMIT)).all()
    arcs = open_arcs(s, character.id)
    # 人物が知っているアイデアのうち、目の前の出来事・企て・方向づけに名前の出るものを渡す
    mentioned = "\n".join([*(event.name for event in recent), *(arc.name for arc in arcs), nudge or ""])
    prompt = ActorSerialized(
        time=time, location_name=s.get_one(Location, pick.location_id).name,
        knowledge=knowledge_of(s, character.id, time, mentioned, None),
        present=[PresentPerson(character_id=other.id, name=other.name if other.id in known_ids else None,
                               looks=appearance_of(s, other, time)) for other in present],
        recent_events=[event.name for event in recent], arcs=arcs, seeds=seeds, nudge=nudge,
    ).model_dump()
    return ActorBrief(prompt=prompt, present_ids=[other.id for other in present], arcs=arcs)


def _arc_id(s: Session, form: ActSaveForm) -> int | None:
    """続ける企てか、新しく始める企て(親の出来事。終わりは空のまま)。"""
    intent = form.intent
    if intent.arc_id is not None and any(arc.id == intent.arc_id for arc in open_arcs(s, form.actor_id)):
        return intent.arc_id
    if not (intent.new_arc_name or "").strip():
        return None
    arc = Event(name=intent.new_arc_name, text=intent.aim, time=form.time, start=form.time, location_id=form.location_id,
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
    arc_id = _arc_id(s, form)
    record = progress.save_progress(s, form.location_id, characters, form.time, form.destinations, form.outcome)
    if form.actor_id not in [link.character_id for link in record.event_characters]:
        record.event_characters.append(EventCharacter(character_id=form.actor_id))
    record.parent_event_id = arc_id
    s.flush()
    idea_ids = _add_ideas(s, form, set(participant_ids))
    moves = allowed_moves(form.outcome.character_moves, participant_ids,
                          [destination.id for destination in form.destinations])
    if moves:
        update_locations(s, moves, form.time)
    if arc_id is not None and form.outcome.arc_closed:
        arc = s.get_one(Event, arc_id)
        if arc.end is None:
            arc.end = form.time
            s.flush()
    return ActSaved(event=record_of(s, EventRecord, record), arc_id=arc_id, idea_ids=idea_ids, moves=moves)


def link_new_character(s: Session, link: NewCharacterLink) -> None:
    """一手で現れた人物・対象を、出来事の当事者に入れ、動いた人物との関係を足す。"""
    s.add(EventCharacter(event_id=link.event_id, character_id=link.character_id))
    s.add(CharacterRelation(character_1_id=link.actor_id, character_2_id=link.character_id, relation=link.relation,
                            text="", start=link.time))
    s.flush()
