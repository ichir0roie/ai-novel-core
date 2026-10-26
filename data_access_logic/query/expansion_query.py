#!/usr/bin/env python3
"""世界の展開(`expansion`)の読み出し。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from db.schema import (
    ConflictStatus, Episode, EpisodeCharacter, Event, EventCharacter, Expansion, ExpansionChange, ExpansionConflict,
    Origin,
)
from db.stamp import Stamp


def expansions_select(limit: int, status: str | None, mode: str | None, actor_id: int | None) -> Select:
    query = select(Expansion).order_by(Expansion.id.desc()).limit(limit)
    if status is not None:
        query = query.where(Expansion.status == status)
    if mode is not None:
        query = query.where(Expansion.mode == mode)
    if actor_id is not None:
        query = query.where(Expansion.actor_id == actor_id)
    return query


def change_counts(s: Session, expansion_ids: list[int]) -> dict[int, dict[str, int]]:
    """展開ごとの、変えた行の数(op ごと)。"""
    counts: dict[int, dict[str, int]] = {}
    for expansion_id, op, count in s.execute(
            select(ExpansionChange.expansion_id, ExpansionChange.op, func.count())
            .where(ExpansionChange.expansion_id.in_(expansion_ids))
            .group_by(ExpansionChange.expansion_id, ExpansionChange.op)):
        counts.setdefault(expansion_id, {})[op] = count
    return counts


def open_conflict_counts(s: Session, expansion_ids: list[int]) -> dict[int, int]:
    return dict(s.execute(  # type: ignore[arg-type]
        select(ExpansionConflict.expansion_id, func.count())
        .where(ExpansionConflict.expansion_id.in_(expansion_ids), ExpansionConflict.status == ConflictStatus.OPEN)
        .group_by(ExpansionConflict.expansion_id)).all())


def open_conflicts_select() -> Select:
    return (select(ExpansionConflict).where(ExpansionConflict.status == ConflictStatus.OPEN)
            .order_by(ExpansionConflict.id))


def changes_select(expansion_id: int) -> Select:
    return select(ExpansionChange).where(ExpansionChange.expansion_id == expansion_id).order_by(ExpansionChange.id)


def open_arcs_select(character_id: int) -> Select:
    """人物がまだ追っている企て。人物モードが足した、親の無い・終わりの空いた出来事で、人物が当事者のもの。"""
    return (select(Event)
            .where(Event.origin == Origin.AI, Event.parent_event_id.is_(None), Event.end.is_(None),
                   Event.event_characters.any(EventCharacter.character_id == character_id))
            .order_by(Event.time))


def last_appearance(s: Session, character_id: int) -> Stamp | None:
    """人物が最後に出た出来事・話の時刻。"""
    event_time = s.scalar(select(func.max(func.coalesce(Event.start, Event.time)))
                          .where(Event.event_characters.any(EventCharacter.character_id == character_id)))
    episode_time = s.scalar(select(func.max(Episode.start))
                            .where(Episode.episode_characters.any(EpisodeCharacter.character_id == character_id)))
    times = [Stamp.from_int(value) if isinstance(value, int) else value for value in (event_time, episode_time)]
    dated = [time for time in times if time is not None]
    return max(dated) if dated else None


def last_change_times(s: Session, expansion_id: int) -> dict[tuple[str, int], datetime]:
    """展開の中で行ごとに最後に変えた時刻。"""
    return {(table, row_id): changed_at for table, row_id, changed_at in s.execute(
        select(ExpansionChange.table_name, ExpansionChange.row_id, func.max(ExpansionChange.created_at))
        .where(ExpansionChange.expansion_id == expansion_id)
        .group_by(ExpansionChange.table_name, ExpansionChange.row_id))}
