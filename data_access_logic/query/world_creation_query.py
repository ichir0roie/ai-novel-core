#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import ColumnElement, Select, exists, func, not_, or_, select

from data_access_logic.query.period import alive_at
from db.schema import (
    ChangeOp, Character, CharacterParameter, Event, EventCharacter, Expansion, ExpansionChange, ExpansionMode, Location,
    Stamp,
)


def siblings_area_sum_select(parent_id: int, exclude_id: int | None = None) -> Select:
    query = (select(func.coalesce(func.sum(Location.area), 0))
             .where(Location.parent_id == parent_id))
    return query if exclude_id is None else query.where(Location.id != exclude_id)


def _day_record(event_id: ColumnElement[int]):
    """人物モードの一日が書いた(足した・延ばした)出来事か。"""
    return (select(ExpansionChange.id).join(Expansion, Expansion.id == ExpansionChange.expansion_id)
            .where(ExpansionChange.table_name == Event.__tablename__, ExpansionChange.row_id == event_id,
                   ExpansionChange.op.in_([ChangeOp.ADD.value, ChangeOp.UPDATE.value]),
                   Expansion.mode == ExpansionMode.CHARACTER.value))


def busy_character_ids_select(time: Stamp) -> Select:
    """その時刻に、終わりのある出来事の最中にいる人物。終わりの空いた出来事は一点の出来事として、人物をふさがない。
    人物モードの一日の出来事は、動いた人物だけをふさぐ。一日じゅうの記録なので、朝に一度居合わせただけの人まで
    一日ふさぐと、同じ日に後から動かす人物の目から、その人が決まった居場所ごと消える。"""
    day_record = _day_record(Event.id)
    return (
        select(EventCharacter.character_id).distinct()
        .join(Event, Event.id == EventCharacter.event_id)
        .where(Event.time <= time, Event.end > time,
               or_(not_(exists(day_record)),
                   exists(day_record.where(Expansion.actor_id == EventCharacter.character_id))))
    )


def alive_locations_select(time: Stamp, location_ids: Collection[int], limit: int) -> Select:
    """`location_ids` のうち、その時刻にある場所を id の順に。"""
    return (select(Location)
            .where(Location.id.in_(list(location_ids)), alive_at(Location, time))
            .order_by(Location.id)
            .limit(limit))


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
