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


def active_locations_select(time: Stamp, place_ids: Collection[int]) -> Select:
    """`place_ids` のうち、その時刻にあって、ランダム生成の対象(`active_random_generation`)の場所。"""
    return select(Location).where(
        Location.id.in_(list(place_ids)), alive_at(Location, time), Location.active_random_generation.is_(True))


def character_active_condition() -> ColumnElement[bool]:
    """ランダム生成の対象になる人物(サブキャラクター)。"""
    return Character.main_character.is_(False)


def alive_characters_select(time: Stamp) -> Select:
    """誕生・死亡は列を持たず `character_parameter` の行で表す(`Character.start` / `.end` を見る)。

    誕生 = 一番早く始まる行の start(`Character.start` と同じ計算)。
    死亡済みかは、一番後に始まる行(無ければ一番後に作った行。`Character.end` と同じ行)の end だけを見る
    (途中の行の end は、育ちなどの区切りで死亡ではないことがあるため)。
    """
    born = (select(func.min(CharacterParameter.start))
            .where(CharacterParameter.character_id == Character.id)
            .correlate(Character).scalar_subquery())
    last_row_id = (
        select(CharacterParameter.id)
        .where(CharacterParameter.character_id == Character.id)
        .order_by(CharacterParameter.start.is_not(None).desc(),
                  CharacterParameter.start.desc(), CharacterParameter.id.desc())
        .limit(1).correlate(Character).scalar_subquery())
    died = (select(CharacterParameter.end)
            .where(CharacterParameter.id == last_row_id)
            .correlate(Character).scalar_subquery())
    return select(Character).where(or_(born.is_(None), born <= time), or_(died.is_(None), died > time))




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


def location_has_story(s: Session, place_id: int) -> bool:
    ancestor_ids = [step.id for step in common_query.place_path(s, place_id)]
    return s.scalar(
        select(Story.id)
        .where(Story.place_id.in_(ancestor_ids))
        .limit(1)
    ) is not None


def check_has_story(s: Session, place_id: int, label: str) -> None:
    if not location_has_story(s, place_id):
        raise ValueError(
            f"{label}: place_id={place_id} には作品が無い。"
            "先に CommitStory でその場所(か祖先)へ作品を置いてから確定する")
