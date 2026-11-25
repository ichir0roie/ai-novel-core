"""人物モード(`SimulateDay`)の db だけの処理。段(`expansion/steps.py`)が呼ぶ。

人物モードは書き手 `ai_append` で書くので、足すことと、`end` で終わりを付けることだけをする(`db/guard.py`)。
"""
from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from ai.instructions.naming import fill_name_placeholder
from data_access_logic import constants
from data_access_logic.character.cast import age_at
from data_access_logic.character.histories import add_history
from data_access_logic.character.knowledge import _related_ids, appearance_of, knowledge_of
from data_access_logic.character.motivations import apply_changes, motivations_at
from data_access_logic.character.moves import allowed_moves, move_destinations, update_locations
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.record import CharacterMotivationRecord, MotivationChange
from data_access_logic.entrypoint import record_of
from data_access_logic.event.plan import _current_location_id
from data_access_logic.event.record import EventRecord
from data_access_logic.event.summary import events_of
from data_access_logic.expansion import budget, needs
from data_access_logic.expansion.act_models import (
    ActFailure, ActionsForm, ArcEvent, AuthorPlan, CharacterDayForm, DayBrief, DayBriefForm, DayCharacter, DayForm,
    DayMaterial, DayMaterialForm, DayPlace, DayPlan, DaySaved, DaySaveForm, DaySerialized, FixedSlot, MotivationLine,
    Motives, NarratedEpisode, NeedMotivationForm, NeedProfile, Needs, NewCharacterLink, ParentArc, ParticipantMotivations,
    PeopleForm, PlacePeople, PresentPerson,
)
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.query import common_query, expansion_query, world_creation_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import (
    CHARACTER_KIND_PERSON, Character, CharacterDay, CharacterLocation, CharacterMotivation, CharacterRelation, Episode,
    EpisodeCharacter, Event, EventAction, EventCharacter, IdeaHistory, IdeaHistoryKnower, Location, Origin,
)
from db.stamp import Stamp, active_calendar

logger = logging.getLogger(__name__)


def _cast_of_latest_episode(s: Session) -> list[Character]:
    """本文のある最新の話に登場した(名前だけでない)人物。"""
    episode = expansion_query.latest_written_episode(s)
    if episode is None:
        raise ValueError("本文のある話が無いので、動かす人物を決められない。人物を渡す")
    return list(s.scalars(
        select(Character).join(EpisodeCharacter, EpisodeCharacter.character_id == Character.id)
        .where(EpisodeCharacter.episode_id == episode.id, EpisodeCharacter.mentioned.is_(False),
               Character.kind == CHARACTER_KIND_PERSON)
        .order_by(Character.id)).all())


def _day_start(s: Session, date: Stamp | None, characters: Sequence[Character]) -> Stamp:
    """動かす日の 0 時(文脈の暦)。日を省けば、人物が最後に出た日のうち一番遅い日の翌日。"""
    if date is None:
        lasts = [last for last in (expansion_query.last_appearance(s, character.id) for character in characters)
                 if last is not None]
        if not lasts:
            raise ValueError("人物が出た話・出来事が無いので、動かす日を決められない。date を渡す")
        date = max(lasts).plus_days(1)
    year, month, day = date.digits[:3]
    return Stamp(year, month, day)


def _hours_of(day_start: Stamp) -> list[Stamp]:
    year, month, day = day_start.digits[:3]
    calendar = active_calendar()
    hours_per_day = 24 if calendar is None else calendar.hours_per_day
    return [Stamp(year, month, day, hour) for hour in range(hours_per_day)]


def _hour_seconds() -> int:
    calendar = active_calendar()
    return 3600 if calendar is None else calendar.hour_seconds


def _area_of(s: Session, location: Location) -> Location | None:
    """詳細の場所の、一番近い詳細でない上の場所。詳細の場所でなければ None。"""
    if not location.map_detail:
        return None
    seen = {location.id}
    current = location
    while current.map_detail:
        if current.parent_id is None or current.parent_id in seen:
            return None
        parent = s.get(Location, current.parent_id)
        if parent is None:
            return None
        seen.add(parent.id)
        current = parent
    return current


def _places_of(s: Session, area: Location, time: Stamp) -> list[DayPlace]:
    """エリアから詳細の場所だけをたどって届く、その時刻にある場所(段の浅い順、同じ段は id の順)。"""
    places: list[DayPlace] = []
    names = {area.id: area.name}
    frontier = [area.id]
    while frontier:
        children = s.scalars(
            select(Location).where(Location.parent_id.in_(frontier), Location.map_detail.is_(True))
            .order_by(Location.id)).all()
        alive = [child for child in children
                 if (child.start is None or child.start <= time) and (child.end is None or child.end > time)]
        for child in alive:
            names[child.id] = child.name
            places.append(DayPlace(id=child.id, name=child.name, kind=child.kind,
                                   parent_name=names.get(child.parent_id) if child.parent_id is not None else None))
        frontier = [child.id for child in alive]
    return places


def _hour_index(hours: list[Stamp], time: Stamp) -> int:
    """`time` を含む一時間の番号。日の始まりより前なら 0。"""
    return max((index for index, hour in enumerate(hours) if hour <= time), default=0)


def _span_hours(start: Stamp, end: Stamp | None) -> int:
    """予定が埋める時間(暦の一時間で数え、上限で切る)。"""
    if end is None or end <= start:
        return constants.DAY_FIXED_DEFAULT_HOURS
    return max(1, min(math.ceil(start.seconds_until(end) / _hour_seconds()), constants.DAY_FIXED_MAX_HOURS))


def _fixed_slots(s: Session, character_id: int, home_id: int, hours: list[Stamp], day_end: Stamp) -> list[FixedSlot]:
    """作者の話(プロットのあるもの)と出来事のうち、その日に始まり、人物が登場人物・当事者のもの。話を先に埋め、重なる時間は先に埋めた方。"""
    episodes = s.scalars(
        select(Episode).where(
            Episode.start >= hours[0], Episode.start < day_end, Episode.plot_text != "",
            Episode.episode_characters.any(
                (EpisodeCharacter.character_id == character_id) & EpisodeCharacter.mentioned.is_(False)))
        .order_by(Episode.start, Episode.id)).all()
    events = s.scalars(
        select(Event).where(
            Event.origin == Origin.USER, Event.time >= hours[0], Event.time < day_end,
            Event.event_characters.any(EventCharacter.character_id == character_id))
        .order_by(Event.time, Event.id)).all()
    slots: dict[int, FixedSlot] = {}
    for episode in episodes:
        assert episode.start is not None
        first = _hour_index(hours, episode.start)
        for hour in range(first, min(first + _span_hours(episode.start, episode.end), len(hours))):
            slots.setdefault(hour, FixedSlot(
                hour=hour, location_id=episode.location_id or home_id, episode_id=episode.id,
                label=f"話「{episode.title}」: {episode.plot_text[:constants.DAY_FIXED_LABEL_LETTERS]}"))
    for event in events:
        first = _hour_index(hours, event.time)
        for hour in range(first, min(first + _span_hours(event.time, event.end), len(hours))):
            slots.setdefault(hour, FixedSlot(
                hour=hour, location_id=event.location_id or home_id, event_id=event.id,
                label=f"出来事「{event.name}」: {event.text[:constants.DAY_FIXED_LABEL_LETTERS]}"))
    return [slots[hour] for hour in sorted(slots)]


def _start_needs(s: Session, character_id: int, day_start: Stamp) -> Needs:
    """前の日の最後の一時間の欲を引き継ぐ。前の日に動いていなければ、夜中の様子から始める。"""
    last = s.scalars(
        select(EventAction).where(EventAction.character_id == character_id, EventAction.time < day_start,
                                  EventAction.time >= day_start.plus_days(-2))
        .order_by(EventAction.time.desc(), EventAction.id.desc()).limit(1)).first()
    if last is None:
        return Needs(hunger=constants.DAY_INITIAL_HUNGER, desire=constants.DAY_INITIAL_DESIRE)
    return Needs(hunger=last.hunger, desire=last.desire)


def _previous_date(day_start: Stamp) -> Stamp:
    """暦の前の日の 0 時。"""
    calendar = active_calendar()
    if calendar is None:
        return day_start.plus_days(-1)
    year, month, day = day_start.digits[:3]
    if day > 1:
        return Stamp(year, month, day - 1)
    if month > 1:
        return Stamp(year, month - 1, calendar.month_days[month - 2])
    return Stamp(year - 1, len(calendar.month_days), calendar.month_days[-1])


def _recent_days(s: Session, character_id: int, day_start: Stamp) -> list[CharacterDay]:
    """その日より前の `DAY_LOOKBACK_DAYS - 1` 日の記録(新しい順)。暦の日付をさかのぼって数える。"""
    dates = [day_start]
    for _ in range(constants.DAY_LOOKBACK_DAYS - 1):
        dates.append(_previous_date(dates[-1]))
    return list(s.scalars(select(CharacterDay).where(
        CharacterDay.character_id == character_id, CharacterDay.date.in_(dates[1:]))
        .order_by(CharacterDay.date.desc())).all())


def _profile(s: Session, character: Character, day_start: Stamp, hours_per_day: int,
             days: list[CharacterDay]) -> tuple[NeedProfile, dict[str, int]]:
    """欲の段と、前の日の不足から決めるその日の欲の強さ・眠りの段取り・行動量と、さかのぼった不足から決める欲のモチベーションの強さ。"""
    values = parameters_at(character, day_start)
    appetite, sleep_drive, libido = needs.levels_of(values, age_at(character, day_start))
    previous_date = _previous_date(day_start)
    previous = next((day for day in days if day.date == previous_date), None)
    required = needs.sleep_plan(hours_per_day, sleep_drive, 0, 0, 0)[0]
    load_before = sum(day.load for day in days)
    maximum = needs.load_max(str(values.proactivity))
    strongest = max((row.strength for row in motivations_at(s, character.id, day_start)), default=0)
    spare = maximum > 0 and load_before < constants.DAY_SPARE_LOAD_RATIO * maximum
    eager = round((int(strongest >= constants.DAY_EAGER_STRENGTH) + int(spare)) * hours_per_day / 24)
    _, wake, bed = needs.sleep_plan(
        hours_per_day, sleep_drive, needs.sleep_debt(None if previous is None else previous.sleep, required),
        0 if previous is None else previous.bedtime - hours_per_day, eager)
    profile = NeedProfile(
        appetite=appetite, sleep_drive=sleep_drive, libido=libido,
        food_pressure=needs.pressure(None if previous is None else previous.food),
        touch_pressure=needs.pressure(None if previous is None else previous.touch),
        required_sleep=required, prev_bed=0 if previous is None else previous.bedtime - hours_per_day,
        wake=wake, bed=bed, load_before=load_before, load_max=maximum)
    shortages = {"food": sum(100 - day.food for day in days), "sleep": sum(100 - day.sleep for day in days),
                 "touch": sum(100 - day.touch for day in days)}
    return profile, {key: needs.motivation_strength(total) for key, total in shortages.items()}


def _day_character(s: Session, character: Character, hours: list[Stamp], day_end: Stamp) -> DayCharacter:
    """人物の一日の始まりの様子。動かせなければ、わけを添えて止める。"""
    label = f"{character.name}(id={character.id})"
    day_start = hours[0]
    if character.end is not None and character.end <= day_start:
        raise ValueError(f"{label}は {day_start} にはもういない(没年 {character.end})")
    location_id = _current_location_id(character, day_start)
    if location_id is None:
        raise ValueError(f"{label}の {day_start} の居場所が分からない")
    location = s.get_one(Location, location_id)
    area = _area_of(s, location)
    if area is None:
        raise ValueError(f"{label}のいる「{location.name}」(id={location.id})は詳細の場所でないので、一日を動かせない。"
                         "詳細マップに場所を足し、人物の居場所をそこへ移す")
    done = s.scalar(select(func.count()).select_from(EventAction).where(
        EventAction.character_id == character.id, EventAction.time >= day_start, EventAction.time < day_end))
    if done:
        raise ValueError(f"{label}の {day_start} の一日は、もう動かしてある(行動 {done} 件)。動かし直すなら、その展開を取り消す")
    profile, strengths = _profile(s, character, day_start, len(hours), _recent_days(s, character.id, day_start))
    return DayCharacter(character_id=character.id, name=character.name, area_id=area.id, home_id=location.id,
                        influence=budget.influence_of(character, day_start),
                        fixed=_fixed_slots(s, character.id, location.id, hours, day_end),
                        needs=_start_needs(s, character.id, day_start), profile=profile, need_strengths=strengths)


def plan_day(s: Session, form: DayForm) -> DayPlan:
    """動かす人物ごとに、一日の始まりの様子と、エリアの行ける場所を決める。動かせない人物は失敗として返す。"""
    if form.character_ids:
        characters = [common_query.get_row(s, Character, id_) for id_ in dict.fromkeys(form.character_ids)]
    else:
        characters = _cast_of_latest_episode(s)
    if len(characters) > constants.DAY_CHARACTER_LIMIT:
        raise ValueError(f"一度に動かせるのは {constants.DAY_CHARACTER_LIMIT} 人まで({len(characters)} 人を渡した)")
    if form.parent_event_id is not None:
        common_query.get_row(s, Event, form.parent_event_id)
    day_start = _day_start(s, form.date, characters)
    hours = _hours_of(day_start)
    day_end = day_start.plus_days(1) if active_calendar() is None else Stamp(*_next_date(day_start))
    plan = DayPlan(date=day_start, hours=hours, day_end=day_end, parent_event_id=form.parent_event_id)
    for character in characters:
        try:
            if character.custom_stamp_id != characters[0].custom_stamp_id:
                raise ValueError(f"{character.name}(id={character.id})は {characters[0].name} と暦が違うので、同じ一日を動かせない")
            day_character = _day_character(s, character, hours, day_end)
        except ValueError as error:
            plan.failed.append(ActFailure(character_id=character.id, name=character.name, error=str(error)))
            continue
        plan.characters.append(day_character)
        if day_character.area_id not in plan.places:
            plan.places[day_character.area_id] = _places_of(s, s.get_one(Location, day_character.area_id), day_start)
    return plan


def _next_date(day_start: Stamp) -> tuple[int, int, int]:
    """暦の次の日付。月・年の終わりをまたぐ。"""
    calendar = active_calendar()
    assert calendar is not None
    year, month, day = day_start.digits[:3]
    if day < calendar.month_days[month - 1]:
        return year, month, day + 1
    if month < len(calendar.month_days):
        return year, month + 1, 1
    return year + 1, 1, 1


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


def day_brief(s: Session, form: DayBriefForm) -> DayBrief:
    """一日のあいだ変わらない人物の目の材料。知ることのできるデータ(知る相手で絞った来歴・関係・アイデア)と、本人の思い・前後の出来事。"""
    character = common_query.get_row(s, Character, form.character_id)
    prompt = DaySerialized(
        time=form.time,
        knowledge=knowledge_of(s, character.id, form.time, form.nudge or "", None, None, with_now=False),
        motives=motives_of(s, character, form.time), seeds=form.seeds, nudge=form.nudge,
    ).model_dump()
    return DayBrief(character_id=character.id, name=character.name, prompt=prompt,
                    known_ids=_related_ids(s, character, form.time))


def _residents_here(s: Session, location_id: int, time: Stamp, exclude_ids: set[int]) -> list[Character]:
    """その場所に住まいがあり、その時刻に生きて手の空いた人物(動かしている人物は除く)。"""
    busy_ids = set(s.scalars(world_creation_query.busy_character_ids_select(time)).all())
    characters = s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(Character.locations.any(CharacterLocation.location_id == location_id))
        .order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in exclude_ids and character.id not in busy_ids
            and _current_location_id(character, time) == location_id]


def people_at(s: Session, form: PeopleForm) -> list[PlacePeople]:
    """動かしている人物のいる場所ごとに、そこにいる人物(動かしている人物を先に、住まいのある人物を続ける。上限まで)。"""
    simulated = set(form.positions)
    by_place: dict[int, list[int]] = {}
    for character_id, location_id in form.positions.items():
        by_place.setdefault(location_id, []).append(character_id)
    places = []
    for location_id, ids in by_place.items():
        people = [s.get_one(Character, id_) for id_ in sorted(ids)]
        people += _residents_here(s, location_id, form.time, simulated)
        places.append(PlacePeople(
            location_id=location_id, location_name=s.get_one(Location, location_id).name,
            people=[PresentPerson(character_id=person.id, name=person.name, looks=appearance_of(s, person, form.time))
                    for person in people[:constants.ACT_PRESENT_LIMIT]]))
    return places


def save_actions(s: Session, form: ActionsForm) -> None:
    for action in form.actions:
        s.add(EventAction(
            character_id=action.character_id, expansion_id=form.expansion_id, time=action.time, location_id=action.location_id,
            kind=action.kind, text=action.text, speech=action.speech, thought=action.thought,
            sleepiness=action.sleepiness, hunger=action.hunger, desire=action.desire, load=action.load,
            fixed_event_id=action.fixed_event_id,
            fixed_episode_id=action.fixed_episode_id))
    s.flush()


def save_character_day(s: Session, form: CharacterDayForm) -> None:
    s.add(CharacterDay(character_id=form.character_id, expansion_id=form.expansion_id, date=form.date, food=form.food,
                       sleep=form.sleep, touch=form.touch, load=form.load, bedtime=form.bedtime))
    s.flush()


def need_motivations(s: Session, form: NeedMotivationForm) -> list[CharacterMotivationRecord]:
    """欲を満たしたいモチベーションを、さかのぼった不足で決めた強さにそろえる(足す・強さを変える・終える)。足した行を返す。"""
    changes = []
    for key, strength in form.strengths.items():
        text = constants.DAY_NEED_MOTIVATIONS[key]
        current = s.scalars(select(CharacterMotivation).where(
            CharacterMotivation.character_id == form.character_id, CharacterMotivation.text == text,
            CharacterMotivation.start <= form.time,
            (CharacterMotivation.end.is_(None)) | (CharacterMotivation.end > form.time))
            .order_by(CharacterMotivation.start.desc())).first()
        if current is None and strength:
            changes.append(MotivationChange(character_id=form.character_id, motivation_id=None, strength=strength,
                                            text=text))
        elif current is not None and current.strength != strength:
            changes.append(MotivationChange(character_id=form.character_id, motivation_id=current.id, strength=strength,
                                            text=None))
    added = apply_changes(s, changes, [form.character_id], form.time)
    return [CharacterMotivationRecord.model_validate(row) for row in added]


def _distance_days(episode: Episode, time: Stamp) -> int:
    assert episode.start is not None
    end = episode.end or episode.start
    if episode.start <= time <= end:
        return 0
    return min(abs(time.days_until(episode.start)), abs(time.days_until(end)))


def related_episodes(s: Session, characters: list[Character], time: Stamp) -> list[NarratedEpisode]:
    """その日の前後 `ACT_NARRATOR_EPISODE_DAYS` 日にかかる、プロットつきの話のうち、`characters` の誰かが登場人物に結ばれているか、
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
    """親の出来事と、その先祖(一番上まで)と、親の子のうちその日の前・後に近いものを上限まで。"""
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


def day_material(s: Session, form: DayMaterialForm) -> DayMaterial:
    """一日を記録する段の材料。影響の枠・居合わせた人物の思い・住まいを移せる先・作者が置いた筋と前後の話。"""
    actor = common_query.get_row(s, Character, form.actor_id)
    participants = [s.get_one(Character, id_) for id_ in dict.fromkeys(form.participant_ids) if id_ != actor.id]
    people = [actor, *participants]
    return DayMaterial(
        frame=budget.frame(actor, people, form.date),
        motivations=[ParticipantMotivations(
            character_id=person.id, name=person.name,
            motivations=[MotivationLine.model_validate(row) for row in motivations_at(s, person.id, form.date)])
            for person in people],
        destinations=move_destinations(s, form.home_id, form.date),
        plan=AuthorPlan(parent=None if form.parent_event_id is None else parent_arc(s, form.parent_event_id, form.date),
                        episodes=related_episodes(s, people, form.date)))


def _add_ideas(s: Session, form: DaySaveForm, participant_ids: set[int]) -> list[int]:
    """一日で生まれた・広まった事柄を、アイデアと照らして(無ければ候補として足し)、この場所・時刻からの呼び名の行を、知った人物を
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


def save_day(s: Session, form: DaySaveForm) -> DaySaved:
    """記録した一日を、出来事一件と、当事者の来歴・事柄の呼び名・住まいの移動・思いの増減として足す。"""
    participant_ids = [form.actor_id, *(id_ for id_ in form.participant_ids if id_ != form.actor_id)]
    by_id = {id_: s.get_one(Character, id_) for id_ in participant_ids}
    outcome = form.outcome
    destination_ids = [destination.id for destination in form.destinations]
    moves = allowed_moves(outcome.character_moves, participant_ids, destination_ids)
    involved_ids = [form.actor_id, *(id_ for id_ in dict.fromkeys(outcome.character_ids)
                                     if id_ in by_id and id_ != form.actor_id)]
    involved_ids += [move.character_id for move in moves if move.character_id not in involved_ids]
    record = Event(name=outcome.event_name, text=outcome.event_text, time=form.time, end=form.end,
                   location_id=form.location_id, parent_event_id=form.parent_event_id,
                   event_characters=[EventCharacter(character_id=id_) for id_ in involved_ids])
    s.add(record)
    for update in outcome.character_updates:
        character = by_id.get(update.character_id)
        if character is not None and update.text:
            add_history(character, form.time, fill_name_placeholder(update.text, character.name or ""))
    s.flush()
    idea_ids = _add_ideas(s, form, set(participant_ids))
    if moves:
        update_locations(s, moves, form.time)
    motivations = apply_changes(s, outcome.motivation_changes, participant_ids, form.time)
    return DaySaved(event=record_of(s, EventRecord, record), idea_ids=idea_ids, moves=moves,
                    motivations=[CharacterMotivationRecord.model_validate(row) for row in motivations])


def link_new_character(s: Session, link: NewCharacterLink) -> None:
    """一日で現れた人物・対象を、出来事の当事者に入れ、動いた人物との関係を足す。"""
    s.add(EventCharacter(event_id=link.event_id, character_id=link.character_id))
    s.add(CharacterRelation(character_1_id=link.actor_id, character_2_id=link.character_id, relation=link.relation,
                            text="", start=link.time))
    s.flush()
