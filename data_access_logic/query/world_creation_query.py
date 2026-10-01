#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import ColumnElement, Select, func, or_, select

from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import (
    Character, CharacterParameter, Event, EventCharacter, Location, Session, Stamp, Story,
)


def siblings_area_sum_select(parent_id: int) -> Select:
    return (select(func.coalesce(func.sum(Location.area), 0))
            .where(Location.parent_id == parent_id))


def busy_character_ids_select(time: Stamp) -> Select:
    return (
        select(EventCharacter.character_id).distinct()
        .join(Event, Event.id == EventCharacter.event_id)
        .where(
            Event.start.is_not(None),
            Event.start <= time,
            or_(Event.end.is_(None), Event.end > time))
    )


def active_locations_select(time: Stamp, location_ids: Collection[int]) -> Select:
    """`location_ids` のうち、その時刻にあって、ランダム生成の対象(`active_random_generation`)の場所。"""
    return select(Location).where(
        Location.id.in_(list(location_ids)), alive_at(Location, time), Location.active_random_generation.is_(True))


def character_active_condition() -> ColumnElement[bool]:
    """ランダム生成の対象になる人物(サブキャラクター)。"""
    return Character.main_character.is_(False)


def alive_characters_select(time: Stamp) -> Select:
    """誕生は列を持たず、`character_parameter` の一番早く始まる行の start で表す(`Character.start` と同じ計算)。"""
    born = (select(func.min(CharacterParameter.start))
            .where(CharacterParameter.character_id == Character.id)
            .correlate(Character).scalar_subquery())
    return select(Character).where(or_(born.is_(None), born <= time), or_(Character.end.is_(None), Character.end > time))




def check_within_parent_span(parent: Location, child_start: Stamp | None, child_end: Stamp | None, label: str) -> None:
    if parent.start is not None:
        if child_start is not None and child_start < parent.start:
            raise ValueError(
                f"{label}: start={child_start} が親(id={parent.id})の "
                f"start={parent.start} より前")
    if parent.end is not None:
        if child_start is not None and child_start >= parent.end:
            raise ValueError(
                f"{label}: start={child_start} が親(id={parent.id})の "
                f"end={parent.end} 以後")
        if child_end is not None and child_end > parent.end:
            raise ValueError(
                f"{label}: end={child_end} が親(id={parent.id})の "
                f"end={parent.end} を超える")


def location_has_story(s: Session, location_id: int) -> bool:
    ancestor_ids = [step.id for step in common_query.location_path(s, location_id)]
    return s.scalar(
        select(Story.id)
        .where(Story.location_id.in_(ancestor_ids))
        .limit(1)
    ) is not None


def check_has_story(s: Session, location_id: int, label: str) -> None:
    if not location_has_story(s, location_id):
        raise ValueError(
            f"{label}: location_id={location_id} には作品が無い。"
            "先に CommitStory でその場所(か祖先)へ作品を置いてから確定する")
