#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable, Collection
import re

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session, selectinload

from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import dictionary_query
from data_access_logic.query.period import Period, alive_at
from db.schema import (
    Base, Character, CharacterLocation, CharacterRelation, CharacterSkill, Episode, Event, EventCharacter, Idea,
    Location, Story,
)
from db.stamp import Stamp, StampError

# 当事者は名前と id しか使わないので、人物の selectin の子の表(パラメータ・居場所・来歴・知る相手)は読まない
EVENT_LOAD_OPTIONS = (
    selectinload(Event.location),
    selectinload(Event.event_characters).selectinload(EventCharacter.character).lazyload("*"),
)


# ---------------------------------------------------------------- 時刻

def span(when: Stamp | str | int) -> tuple[Stamp, Stamp]:
    text = str(when).strip()
    at = Stamp.parse(text)
    if at is None:
        raise StampError("時刻が空")
    depth = 1 if text.isdigit() else len(
        [part for part in re.split(r"[-/ :T]", text) if part])
    parts = [at.year, at.month, at.day, at.hour, at.minute, at.second]
    largest = [None, 12, 31, 23, 59, 59]
    for index in range(min(depth, 6), 6):
        parts[index] = largest[index]
    return at, Stamp(*parts)


def resolve_time(s: Session, when: Stamp | str | None, story: Story | None) -> tuple[Stamp, Stamp]:
    if when is not None:
        return span(when)
    latest = s.scalar(select(func.max(Episode.start)).where(Episode.story_id == story.id)) if story else None
    if latest is not None:
        return span(latest)
    raise ValueError("時刻が決まらない(作品に時刻の決まった話が無いので time を渡す)")


def get_row[M: Base](s: Session, model: type[M], id_: int) -> M:
    row = s.get(model, id_)
    if row is None:
        raise UnknownRecordError(f"id={id_} の {model.__tablename__} が見つからない")
    return row


def _in_span(column: InstrumentedAttribute[Stamp], since: Stamp, until: Stamp) -> ColumnElement[bool]:
    # 列は `StampType` なので、`Stamp` のまま渡す(整数を渡すと年として読まれる)
    return column.between(since, until)


def latest_time_select() -> Select:
    return select(func.max(Event.time))


# ---------------------------------------------------------------- 場所の木

def descendant_location_ids(s: Session, location_id: int) -> list[int]:
    """何段あるか分からないので一段ずつたどる。"""
    get_row(s, Location, location_id)
    found = [location_id]
    frontier = [location_id]
    while frontier:
        children = s.scalars(
            select(Location.id).where(Location.parent_id.in_(frontier))).all()
        children = [child for child in children if child not in found]
        found.extend(children)
        frontier = children
    return found


def story_path_ids(s: Session, story_id: int) -> list[int]:
    """親の作品をたどった、一番上の作品からこの作品までの id。上から順"""
    path: list[int] = []
    current: int | None = story_id
    while current is not None and current not in path:
        path.append(current)
        current = get_row(s, Story, current).parent_story_id
    return list(reversed(path))


def descendant_story_ids(s: Session, story_id: int) -> list[int]:
    """この作品とその子孫(章・外伝)の id。何段あるか分からないので一段ずつたどる。"""
    get_row(s, Story, story_id)
    found = [story_id]
    frontier = found
    while frontier:
        children = s.scalars(
            select(Story.id).where(Story.parent_story_id.in_(frontier))).all()
        children = [child for child in children if child not in found]
        found = found + children
        frontier = children
    return found


def idea_scope_ids(s: Session, location_id: int) -> list[int]:
    """アイデアの `location_id` は、そこから配下で効く。現在地から最上位までをたどる。"""
    get_row(s, Location, location_id)
    return [step.id for step in reversed(location_path(s, location_id))]


def location_path(s: Session, location_id: int) -> list[LocationMaterial]:
    """最上位の場所から `location_id` までの道筋。"""
    chain: list[LocationMaterial] = []
    seen: set[int] = set()
    current = s.get(Location, location_id)
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(LocationMaterial.model_validate(current))
        current = s.get(Location, current.parent_id) if current.parent_id else None
    return list(reversed(chain))


def location_up(s: Session, location_id: int, levels: int) -> int:
    current = get_row(s, Location, location_id)
    for _ in range(max(0, levels)):
        if current.parent_id is None:
            break
        parent = s.get(Location, current.parent_id)
        if parent is None:
            break
        current = parent
    return current.id


# ---------------------------------------------------------------- 場所

def locations_select(kind: str | None = None) -> Select:
    query = select(Location)
    if kind is not None:
        query = query.where(Location.kind == kind)
    return query.order_by(Location.id.asc())


def planets_select() -> Select:
    return select(Location).where(Location.kind == "星").order_by(Location.id.asc())


def locations_on_planet_select(planet_id: int) -> Select:
    return (
        select(Location)
        .where(Location.location_planet == planet_id)
        .where(Location.location_longitude.is_not(None))
        .where(Location.location_latitude.is_not(None))
        .order_by(Location.id.asc())
    )


def mapped_locations_select() -> Select:
    """星の上にあって、経緯度か輪郭(polygon)を持つ場所。全部の星の分を一度に引く"""
    return (
        select(Location)
        .where(Location.location_planet.is_not(None))
        .where(or_(Location.location_longitude.is_not(None) & Location.location_latitude.is_not(None),
                   Location.polygon.is_not(None)))
        .order_by(Location.id.asc())
    )


# ---------------------------------------------------------------- 出来事

def events_at_select(when: Stamp | str, location_ids: Collection[int] | None = None, limit: int | None = None) -> Select:
    since, until = span(when)
    query = (select(Event)
             .options(*EVENT_LOAD_OPTIONS)
             .where(_in_span(Event.time, since, until)))
    if location_ids is not None:
        query = query.where(Event.location_id.in_(list(location_ids)))
    query = query.order_by(Event.time.desc(), Event.id.desc())
    if limit:
        query = query.limit(limit)
    return query


def _events_where(condition: ColumnElement[bool], until: Stamp | str | None, limit: int | None) -> Select:
    query = select(Event).options(*EVENT_LOAD_OPTIONS).where(condition)
    if until is not None:
        query = query.where(Event.time <= span(until)[1])
    query = query.order_by(Event.time.desc(), Event.id.desc())
    if limit:
        query = query.limit(limit)
    return query


def events_of_location_select(location_id: int, until: Stamp | str | None = None, limit: int | None = 5) -> Select:
    return _events_where(Event.location_id == location_id, until, limit)


def events_of_character_select(character_id: int, until: Stamp | str | None = None, limit: int | None = 5) -> Select:
    return _events_where(
        Event.event_characters.any(EventCharacter.character_id == character_id), until, limit)


def events_under_select(event_id: int, until: Stamp | str | None = None, limit: int | None = 5) -> Select:
    return _events_where(Event.parent_event_id == event_id, until, limit)


def events_after_select(location_id: int | None, character_ids: Collection[int], after: Stamp, limit: int = 5) -> Select:
    """人物ごとに時を刻むので、ある人物の出来事を起こす時点より後に、別の人物の出来事が既にあることがある。
    `location_id` が None なら当事者の出来事だけ(場所の無い出来事まで拾わない)。"""
    conditions = [Event.event_characters.any(EventCharacter.character_id.in_(list(character_ids)))]
    if location_id is not None:
        conditions.append(Event.location_id == location_id)
    return (select(Event)
            .options(*EVENT_LOAD_OPTIONS)
            .where(Event.time > after, or_(*conditions))
            .order_by(Event.time.asc(), Event.id.asc())
            .limit(limit))


def events_select() -> Select:
    return (select(Event)
            .options(*EVENT_LOAD_OPTIONS)
            .order_by(Event.time.desc(), Event.id.desc()))


def open_events_select(location_ids: Collection[int], until: Stamp) -> Select:
    return (select(Event)
            .options(*EVENT_LOAD_OPTIONS)
            .where(Event.location_id.in_(list(location_ids)),
                   Event.time <= until,
                   or_(Event.end.is_(None), Event.end > until),
                   ~Event.event_characters.any())
            .order_by(Event.time.desc(), Event.id.desc()))


# ---------------------------------------------------------------- 人物

def character_location_select(character_id: int, until: Stamp) -> Select:
    return (select(CharacterLocation)
            .options(selectinload(CharacterLocation.location))
            .where(CharacterLocation.character_id == character_id, alive_at(CharacterLocation, until))
            .order_by(CharacterLocation.start.desc().nulls_last(), CharacterLocation.id.desc())
            .execution_options(populate_existing=True))


def resident_character_ids_select(location_ids: Collection[int], until: Stamp) -> Select:
    return (select(CharacterLocation.character_id).distinct()
            .where(CharacterLocation.location_id.in_(list(location_ids)), alive_at(CharacterLocation, until))
            # DISTINCT の並びは db 次第(PostgreSQL は崩れる)なので、id の順に決める
            .order_by(CharacterLocation.character_id))


def resident_names_select(location_ids: Collection[int], until: Stamp) -> Select:
    return (select(Character.name).distinct()
            .join(CharacterLocation, CharacterLocation.character_id == Character.id)
            .where(CharacterLocation.location_id.in_(list(location_ids)), alive_at(CharacterLocation, until),
                   Character.name.is_not(None))
            .order_by(Character.name))


def character_names_select() -> Select:
    return select(Character.name).distinct().where(Character.name.is_not(None)).order_by(Character.name)


def character_select(character_id: int) -> Select:
    return select(Character).where(Character.id == character_id)


def characters_select() -> Select:
    return (select(Character)
            .options(selectinload(Character.locations))
            .order_by(Character.id.asc()))


# ---------------------------------------------------------------- 作品

def stories_select() -> Select:
    return select(Story).order_by(Story.display_order.asc().nulls_last(), Story.id)


def story_location_id(s: Session, story_id: int, until: Stamp) -> int | None:
    """作品の立つ場所。時刻 `until` までで、場所の決まった一番後の話の場所(無ければ None)。"""
    return s.scalar(select(Episode.location_id)
                    .where(Episode.story_id == story_id, Episode.location_id.is_not(None), Episode.start <= until)
                    .order_by(Episode.start.desc(), Episode.id.desc()).limit(1))


def episode_order() -> tuple:
    """作品の中の話の並び。start の順で、start の無い話は後ろに id 順"""
    return (Episode.start.asc().nulls_last(), Episode.id.asc())


def story_episodes_select(story_id: int) -> Select:
    return (select(Episode)
            .where(Episode.story_id == story_id)
            .order_by(*episode_order()))


def episodes_select(story_id: int, count: int = 10, before: Stamp | str | None = None) -> Select:
    """呼び出し側は取り出した後に `reversed()` して古い順に並べ直す
    (新しい順に `limit` するため、select 自体は新しい順のまま返す)。
    `before` は時刻。start がそれより前の話だけに絞る(start の無い話は外れる)。
    """
    query = select(Episode).where(Episode.story_id == story_id)
    if before is not None:
        query = query.where(Episode.start < Stamp.parse(before))
    return query.order_by(Episode.start.desc().nulls_first(), Episode.id.desc()).limit(count)


def unsynced_episodes_select(story_id: int | None = None) -> Select:
    query = (select(Episode)
             .options(selectinload(Episode.story))
             .where(Episode.synced.is_(False)))
    if story_id is not None:
        query = query.where(Episode.story_id == story_id)
    return query.order_by(Episode.story_id, *episode_order())


# ---------------------------------------------------------------- 断面

def ideas_select(location_ids: Collection[int] | None, time: Stamp | None = None) -> Select:
    return (select(Idea)
            .where(dictionary_query.idea_in_scope(location_ids, time))
            .order_by(Idea.id))


def character_relations_at_select(
    character_ids: Collection[int], time: Stamp, period: Callable[[Period, Stamp], ColumnElement[bool]] = alive_at,
) -> Select[CharacterRelation]:
    """`character_ids` のどれかが片側にいて、`time` に続いている(`period` に当たる)関係を、両側の人物と来歴ごと読む。"""
    return (select(CharacterRelation)
            .options(selectinload(CharacterRelation.character_1), selectinload(CharacterRelation.character_2))
            .where(or_(CharacterRelation.character_1_id.in_(character_ids),
                       CharacterRelation.character_2_id.in_(character_ids)),
                   period(CharacterRelation, time))
            .order_by(CharacterRelation.id)
            .execution_options(populate_existing=True))


def character_skills_select(character_id: int) -> Select[CharacterSkill]:
    return (select(CharacterSkill)
            .where(CharacterSkill.character_id == character_id)
            .order_by(CharacterSkill.id)
            .execution_options(populate_existing=True))


def character_relations_select(character_id: int | None = None) -> Select:
    query = select(CharacterRelation)
    if character_id is not None:
        query = query.where(or_(CharacterRelation.character_1_id == character_id,
                                CharacterRelation.character_2_id == character_id))
    return query.order_by(CharacterRelation.id)
