#!/usr/bin/env python3
from __future__ import annotations

import re

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from db.schema import (
    ConfirmStatus,
    Character, CharacterPlace, CharacterRelation, Episode,
    Event, EventCharacter, Idea, Location,
    Story,
)
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import dictionary_query
from db.stamp import Stamp, StampError

EVENT_LOAD_OPTIONS = (
    selectinload(Event.location),
    selectinload(Event.event_characters).selectinload(EventCharacter.character),
)


class NotFoundError(LookupError):
    pass


# ---------------------------------------------------------------- 時刻

def span(when) -> tuple[Stamp, Stamp]:
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


def resolve_time(session: Session, when, story: Story | None) -> tuple[Stamp, Stamp]:
    if when is not None:
        return span(when)
    if story is not None and story.start is not None:
        return span(story.start.year)
    raise ValueError("時刻が決まらない(作品に立つ年が無いので time を渡す)")


def get_row(session: Session, model, id_: int, label: str):
    row = session.get(model, id_)
    if row is None:
        raise NotFoundError(f"{label}={id_} という id の {model.__tablename__} が見つからない")
    return row


def get_story(session: Session, story_id: int) -> Story:
    return get_row(session, Story, story_id, "story_id")


def _in_span(column, since: Stamp, until: Stamp):
    # 列は `StampType` なので、`Stamp` のまま渡す(整数を渡すと年として読まれる)
    return column.between(since, until)


def _alive(model, until: Stamp):
    return (or_(model.start.is_(None), model.start <= until),
            or_(model.end.is_(None), model.end > until))


def latest_time_select() -> Select:
    return select(func.max(Event.time))


# ---------------------------------------------------------------- 場所の木

def descendant_place_ids(session: Session, place_id: int) -> list[int]:
    """何段あるか分からないので一段ずつたどる。"""
    get_row(session, Location, place_id, "place_id")
    found = [place_id]
    frontier = [place_id]
    while frontier:
        children = session.scalars(
            select(Location.id).where(Location.parent_id.in_(frontier))).all()
        children = [child for child in children if child not in found]
        found.extend(children)
        frontier = children
    return found


def idea_scope_ids(session: Session, place_id: int) -> list[int]:
    """アイデアの `location_id` は、そこから配下で効く。現在地から最上位までをたどる。"""
    found = [get_row(session, Location, place_id, "place_id").id]
    current = session.get(Location, place_id)
    while current is not None and current.parent_id and current.parent_id not in found:
        current = session.get(Location, current.parent_id)
        if current is None:
            break
        found.append(current.id)
    return found


def place_path(session: Session, place_id: int) -> list[LocationMaterial]:
    """最上位の場所から `place_id` までの道筋。"""
    chain: list[LocationMaterial] = []
    seen: set[int] = set()
    current = session.get(Location, place_id)
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(LocationMaterial.model_validate(current))
        current = session.get(Location, current.parent_id) if current.parent_id else None
    return list(reversed(chain))


def place_up(session: Session, place_id: int, levels: int) -> int:
    current = get_row(session, Location, place_id, "place_id")
    for _ in range(max(0, levels)):
        if current.parent_id is None:
            break
        parent = session.get(Location, current.parent_id)
        if parent is None:
            break
        current = parent
    return current.id


# ---------------------------------------------------------------- 場所

def places_select(kind: str | None = None) -> Select:
    query = select(Location)
    if kind is not None:
        query = query.where(Location.kind == kind)
    return query.order_by(Location.id.asc())


def planets_select() -> Select:
    return select(Location).where(Location.kind == "星").order_by(Location.id.asc())


def places_on_planet_select(planet_id: int) -> Select:
    return (
        select(Location)
        .where(Location.location_planet == planet_id)
        .where(Location.location_longitude.is_not(None))
        .where(Location.location_latitude.is_not(None))
        .order_by(Location.id.asc())
    )


def shapes_on_planet_select(planet_id: int) -> Select:
    return (
        select(Location)
        .where(Location.location_planet == planet_id)
        .where(Location.polygon.is_not(None))
        .order_by(Location.id.asc())
    )


# ---------------------------------------------------------------- 出来事

def events_at_select(when, place_ids=None, limit=None) -> Select:
    since, until = span(when)
    query = (select(Event)
             .options(*EVENT_LOAD_OPTIONS)
             .where(_in_span(Event.time, since, until)))
    if place_ids is not None:
        query = query.where(Event.location_id.in_(list(place_ids)))
    query = query.order_by(Event.time.desc(), Event.id.desc())
    if limit:
        query = query.limit(limit)
    return query


def events_in_locations_select(place_ids, until=None, limit=None) -> Select:
    query = select(Event).options(*EVENT_LOAD_OPTIONS)
    if place_ids:
        query = query.where(Event.location_id.in_(list(place_ids)))
    if until is not None:
        query = query.where(Event.time <= span(until)[1])
    query = query.order_by(Event.time.desc(), Event.id.desc())
    if limit:
        query = query.limit(limit)
    return query


def _events_where(condition, until, limit) -> Select:
    query = select(Event).options(*EVENT_LOAD_OPTIONS).where(condition)
    if until is not None:
        query = query.where(Event.time <= span(until)[1])
    query = query.order_by(Event.time.desc(), Event.id.desc())
    if limit:
        query = query.limit(limit)
    return query


def events_of_place_select(place_id: int, until=None, limit=5) -> Select:
    return _events_where(Event.location_id == place_id, until, limit)


def events_of_character_select(character_id: int, until=None, limit=5) -> Select:
    return _events_where(
        Event.event_characters.any(EventCharacter.character_id == character_id), until, limit)


def events_under_select(event_id: int, until=None, limit=5) -> Select:
    return _events_where(Event.parent_event_id == event_id, until, limit)


def events_after_select(place_id: int | None, character_ids, after: Stamp, limit=5) -> Select:
    """人物ごとに時を刻むので、ある人物の出来事を起こす時点より後に、別の人物の出来事が既にあることがある。
    `place_id` が None なら当事者の出来事だけ(場所の無い出来事まで拾わない)。"""
    conditions = [Event.event_characters.any(EventCharacter.character_id.in_(list(character_ids)))]
    if place_id is not None:
        conditions.append(Event.location_id == place_id)
    return (select(Event)
            .options(*EVENT_LOAD_OPTIONS)
            .where(Event.time > after, or_(*conditions))
            .order_by(Event.time.asc(), Event.id.asc())
            .limit(limit))


def events_select() -> Select:
    return (select(Event)
            .options(*EVENT_LOAD_OPTIONS)
            .order_by(Event.time.desc(), Event.id.desc()))


def open_events_select(place_ids, until: Stamp) -> Select:
    return (select(Event)
            .options(*EVENT_LOAD_OPTIONS)
            .where(Event.location_id.in_(list(place_ids)),
                   Event.time <= until,
                   or_(Event.end.is_(None), Event.end > until),
                   ~Event.event_characters.any())
            .order_by(Event.time.desc(), Event.id.desc()))


# ---------------------------------------------------------------- 人物

def character_place_select(character_id: int, until: Stamp) -> Select:
    return (select(CharacterPlace)
            .options(selectinload(CharacterPlace.place))
            .where(CharacterPlace.character_id == character_id, *_alive(CharacterPlace, until))
            .order_by(CharacterPlace.start.desc(), CharacterPlace.id.desc()))


def latest_character_event_select(character_id: int, until: Stamp | None = None) -> Select:
    finished = func.coalesce(Event.end, Event.start, Event.time)
    query = (select(Event)
             .options(*EVENT_LOAD_OPTIONS)
             .where(Event.event_characters.any(EventCharacter.character_id == character_id))
             .order_by(finished.desc(), Event.id.desc())
             .limit(1))
    return query.where(finished <= until) if until is not None else query


def character_events_overlapping_select(character_id: int, time: Stamp) -> Select:
    started = func.coalesce(Event.start, Event.time)
    finished = func.coalesce(Event.end, Event.start, Event.time)
    return (select(Event)
            .where(Event.event_characters.any(EventCharacter.character_id == character_id),
                   started <= time, finished > time)
            .limit(1))


def resident_character_ids_select(place_ids, until: Stamp) -> Select:
    """話・断面に出す顔ぶれなので、ユーザが確かめた(`confirmed=承認`)人物・対象だけに絞る。"""
    return (select(CharacterPlace.character_id).distinct()
            .join(Character, Character.id == CharacterPlace.character_id)
            .where(CharacterPlace.location_id.in_(list(place_ids)), *_alive(CharacterPlace, until),
                   Character.confirmed == ConfirmStatus.APPROVED))


def character_select(character_id: int) -> Select:
    return select(Character).where(Character.id == character_id)


def characters_select() -> Select:
    return (select(Character)
            .options(selectinload(Character.places))
            .order_by(Character.id.asc()))


# ---------------------------------------------------------------- 作品

def story_select(story_id: int) -> Select:
    return (select(Story)
            .options(selectinload(Story.world), selectinload(Story.place))
            .where(Story.id == story_id))


def stories_select() -> Select:
    return (select(Story)
            .options(selectinload(Story.world), selectinload(Story.place))
            .order_by(Story.id))


def episode_order() -> tuple:
    """作品の中の話の並び。start の順で、start の無い話は後ろに id 順"""
    return (Episode.start.asc().nulls_last(), Episode.id.asc())


def story_episodes_select(story_id: int) -> Select:
    return (select(Episode)
            .where(Episode.story_id == story_id)
            .order_by(*episode_order()))


def episodes_select(story_id: int, count: int = 10, before=None) -> Select:
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

def ideas_select(place_ids, time: Stamp | None = None) -> Select:
    return (select(Idea)
            .where(dictionary_query.idea_in_scope(place_ids, time), Idea.confirmed == ConfirmStatus.APPROVED)
            .order_by(Idea.id))


def character_relations_at_select(character_id: int, time: Stamp) -> Select:
    return (select(CharacterRelation)
            .where(or_(CharacterRelation.character_id_1 == character_id,
                       CharacterRelation.character_id_2 == character_id),
                   or_(CharacterRelation.start.is_(None), CharacterRelation.start <= time),
                   or_(CharacterRelation.end.is_(None), CharacterRelation.end > time))
            .order_by(CharacterRelation.id))


def character_relations_select(character_id: int | None = None) -> Select:
    query = select(CharacterRelation)
    if character_id is not None:
        query = query.where(or_(CharacterRelation.character_id_1 == character_id,
                                CharacterRelation.character_id_2 == character_id))
    return query.order_by(CharacterRelation.id)
