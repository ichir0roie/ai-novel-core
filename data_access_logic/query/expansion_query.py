#!/usr/bin/env python3
"""世界の展開(`expansion`)の読み出し。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.query import common_query
from db.schema import (
    Character, ConflictStatus, Episode, EpisodeCharacter, Event, EventAction, EventCharacter, Expansion, ExpansionChange,
    ExpansionConflict, Origin,
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


def latest_written_episode(s: Session, character_id: int | None = None,
                           story_ids: list[int] | None = None) -> Episode | None:
    """本文のある話のうち、時刻(終わりがあれば終わり)が一番遅いもの。`character_id` を渡せば、その人物が登場した(名前だけでない)話に絞る。
    `story_ids` を渡せば、その作品の話に絞る。"""
    query = (select(Episode).where(Episode.start.is_not(None), Episode.main_text != "")
             .order_by(func.coalesce(Episode.end, Episode.start).desc(), Episode.id.desc()).limit(1))
    if character_id is not None:
        query = query.where(Episode.episode_characters.any(
            (EpisodeCharacter.character_id == character_id) & EpisodeCharacter.mentioned.is_(False)))
    if story_ids is not None:
        query = query.where(Episode.story_id.in_(story_ids))
    return s.scalars(query).first()


def episode_time(episode: Episode) -> Stamp:
    """話の時刻。終わりがあれば終わり。"""
    time = episode.end or episode.start
    assert time is not None
    return time


def _stamp(value: Stamp | int | None) -> Stamp | None:
    return Stamp.from_int(value) if isinstance(value, int) else value


def world_present(s: Session, character: Character) -> Stamp | None:
    """人物の世界の今。人物の作品の一番上の作品と、その下の章・外伝の、本文のある最新の話の時刻。作品の無い人物は None。"""
    if character.story_id is None:
        return None
    root_id = common_query.story_path_ids(s, character.story_id)[0]
    episode = latest_written_episode(s, story_ids=common_query.descendant_story_ids(s, root_id))
    return None if episode is None else episode_time(episode)


def last_appearance(s: Session, character_id: int) -> Stamp | None:
    """人物が最後に出た時刻。本文のある話に登場していれば、その話の時刻と、それより後に AI が足した当事者の出来事のうち遅い方。
    作者の出来事とプロットだけの話は、先の筋として置かれていることがあるので数えない(数えると、人物がその先へ飛ぶ)。
    登場した話が無ければ、当事者の出来事の一番遅い時刻(作者の出来事は、世界の今より後のものを数えない)。
    人物モードで動いた一日は、行動の表の時刻でも数える(前の日の出来事を延ばして続けた日は、出来事の始まりが前の日のままなので)。
    世界の今(`world_present`)から `ACT_STALE_DAYS` 日より前に取り残された人物は、その時刻に生きていれば世界の今に寄せる
    (昔の章にだけ出た人物が、過去に戻って動かないように)。"""
    character = common_query.get_row(s, Character, character_id)
    present = world_present(s, character)
    events = select(func.max(Event.time)).where(Event.event_characters.any(EventCharacter.character_id == character_id))
    acted = _stamp(s.scalar(select(func.max(EventAction.time)).where(EventAction.character_id == character_id)))
    episode = latest_written_episode(s, character_id)
    if episode is None:
        last = _stamp(s.scalar(
            events if present is None else events.where((Event.origin == Origin.AI) | (Event.time <= present))))
    else:
        since = episode_time(episode)
        last = _stamp(s.scalar(events.where(Event.origin == Origin.AI, Event.time > since))) or since
        acted = acted if acted is not None and acted > since else None
    last = max(filter(None, (last, acted)), default=None)
    stale = present is not None and (last is None or last.plus_days(constants.ACT_STALE_DAYS) < present)
    if stale and (character.end is None or character.end > present):
        return present
    return last


def last_change_times(s: Session, expansion_id: int) -> dict[tuple[str, int], datetime]:
    """展開の中で行ごとに最後に変えた時刻。"""
    return {(table, row_id): changed_at for table, row_id, changed_at in s.execute(
        select(ExpansionChange.table_name, ExpansionChange.row_id, func.max(ExpansionChange.created_at))
        .where(ExpansionChange.expansion_id == expansion_id)
        .group_by(ExpansionChange.table_name, ExpansionChange.row_id))}
