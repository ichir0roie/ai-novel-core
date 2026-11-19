#!/usr/bin/env python3
"""西暦で入れてきた時刻を、暦の桁として読み替えて移す入口。作品に暦を付けた直後に一度だけ回す。

暦を付ける前は、作中の時刻を西暦の桁で入れていた(`11592/03/15`)。暦を付けると同じ桁が別の時刻を指すので、
この暦で数える作品の行のうち、暦の始まり(`offset`)から後の時刻を、日付の桁を保ったまま西暦の値だけ移す。画面に出る日付は
変わらない。時・分は、暦の一日の長さが西暦と違えば、一日のうちの割合を保って移す(正午は正午のまま)。
展開の取り消しに控えた値(`expansion_change.before`。西暦の表記で控える)も同じく移す。
桁が暦に無い値(暦の一日の時間を超える時など)は移さずに数えて返す。
二度回すと二度ずれるので、`dry_run` で数を確かめてから一度だけ書く。書き直しは直した時刻(`updated_at`)を進めず、
行の出自(AI の行か)も変えない(`db.writer.rewriting`)。
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.custom_stamp.record import ShiftResult, ShiftSample
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story import scope
from db import writer
from db.postgres.timestamps import keep_updated_at
from db.schema import Base, ChangeOp, CustomStamp, ExpansionChange, StampType, Story
from db.stamp import Calendar, Stamp, StampError, using_calendar

_SAMPLE_COUNT = 5


def calendar_story_ids(s: Session, custom_stamp_id: int) -> set[int]:
    """この暦で数える作品(暦を持たない子孫を含む)。"""
    stories = {story.id: story for story in s.scalars(select(Story))}
    found = set()
    for story_id in stories:
        current, seen = stories.get(story_id), set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.custom_stamp_id is not None:
                if current.custom_stamp_id == custom_stamp_id:
                    found.add(story_id)
                break
            current = stories.get(current.parent_story_id) if current.parent_story_id is not None else None
    return found


def _stamp_columns(model: type[Base]) -> list[str]:
    return [column.key for column in model.__table__.columns if isinstance(column.type, StampType)]


# 消えた行の、消す前の値(表の名前と行の id から)。親の行も同じ展開で消えていれば、その控えからたどる
Deleted = dict[tuple[str, int], dict[str, Any]]
_MAX_DEPTH = 12


def _snapshot_story(s: Session, model: type[Base], row_id: int, before: dict[str, Any] | None, deleted: Deleted,
                    depth: int = 0) -> int | None:
    """控えの行の作品。行が消えていれば、控えた値(作品・親の行の id)からたどる。"""
    found = scope.story_of_row(s, model, row_id)
    if found is not None or before is None or depth > _MAX_DEPTH:
        return found
    if model is Story:
        return row_id
    if before.get("story_id") is not None:
        return before["story_id"]
    for column in model.__table__.columns:
        for foreign_key in column.foreign_keys:
            target = scope.model_of_table(foreign_key.column.table.name)
            value = before.get(column.key)
            if target is None or target is Story or not isinstance(value, int):
                continue
            found = _snapshot_story(s, target, value, deleted.get((target.__tablename__, value)), deleted, depth + 1)
            if found is not None:
                return found
    return None


class _Shift:
    """一回の読み替えの数と見本。"""

    def __init__(self, calendar: Calendar):
        self.calendar = calendar
        self.shifted: Counter[str] = Counter()
        self.outside: Counter[str] = Counter()
        self.invalid: Counter[str] = Counter()
        self.samples: list[ShiftSample] = []
        self.invalid_samples: list[ShiftSample] = []

    def late(self, value: Stamp | None) -> bool:
        return value is not None and value.western_digits >= self.calendar.offset

    def moved(self, table: str, row_id: int, column: str, value: Stamp) -> Stamp | None:
        """桁を保ったまま暦の時刻に移した値。時刻は西暦の一日のつもりで書いてあるので、暦の一日の長さが違えば、一日のうちの
        割合を保って移す(西暦の 12 時は、一日 30 時間の暦の 15 時)。桁が暦に無ければ数えて None。"""
        digits = value.western_digits
        calendar = self.calendar
        if (calendar.hours_per_day, calendar.minutes_per_hour, calendar.seconds_per_minute) != (24, 60, 60):
            digits = calendar.from_western_clock(digits)
        try:
            with using_calendar(calendar):
                moved = Stamp(*digits)
        except StampError:
            self.invalid[table] += 1
            if len(self.invalid_samples) < _SAMPLE_COUNT:
                self.invalid_samples.append(ShiftSample(table=table, id=row_id, column=column,
                                                        before=value.western_text(), after=""))
            return None
        self.shifted[table] += 1
        if len(self.samples) < _SAMPLE_COUNT:
            self.samples.append(ShiftSample(table=table, id=row_id, column=column,
                                            before=value.western_text(), after=moved.western_text()))
        return moved


class ShiftIntoCustomStamp(CommitEntrypoint):
    def __init__(self, custom_stamp_id: int, dry_run: bool = True):
        self.custom_stamp_id = custom_stamp_id
        self.dry_run = dry_run

    def execute(self, s: Session) -> ShiftResult:
        with writer.rewriting():
            return self._shift(s)

    def _shift(self, s: Session) -> ShiftResult:
        row = common_query.get_row(s, CustomStamp, self.custom_stamp_id)
        shift = _Shift(scope.calendar_of_row(row))
        story_ids = calendar_story_ids(s, self.custom_stamp_id)
        if not story_ids:
            raise ValueError(f"custom_stamp_id={self.custom_stamp_id} の暦で数える作品が無い。先に作品の custom_stamp_id に付ける")
        # 行の作品は親の行をたどって決めるので、表をまとめて読んでおき、たどるたびに問い合わせない
        for mapper in Base.registry.mappers:
            s.scalars(select(mapper.class_)).all()
        if not self.dry_run:
            keep_updated_at(s.connection())

        stories: dict[tuple[type[Base], int], int | None] = {}
        for mapper in Base.registry.mappers:
            model = mapper.class_
            columns = _stamp_columns(model)
            if model is CustomStamp or not columns:
                continue
            for record in s.scalars(select(model)):
                late = {key: value for key in columns if shift.late(value := getattr(record, key))}
                if not late:
                    continue
                key = (model, record.id)
                if key not in stories:
                    stories[key] = scope.story_of_row(s, model, record.id)
                if stories[key] not in story_ids:
                    shift.outside[model.__tablename__] += len(late)
                    continue
                for column, value in late.items():
                    moved = shift.moved(model.__tablename__, record.id, column, value)
                    if moved is not None and not self.dry_run:
                        setattr(record, column, moved)

        changes = s.scalars(select(ExpansionChange).where(ExpansionChange.before.is_not(None))).all()
        deleted: Deleted = {(change.table_name, change.row_id): change.before for change in changes
                            if change.op == ChangeOp.DELETE and change.before is not None}
        for change in changes:
            self._shift_snapshot(s, shift, change, story_ids, deleted)
        if not self.dry_run:
            s.flush()
        return ShiftResult(dry_run=self.dry_run, story_ids=sorted(story_ids), shifted=dict(shift.shifted),
                           outside=dict(shift.outside), invalid=dict(shift.invalid), samples=shift.samples,
                           invalid_samples=shift.invalid_samples)

    def _shift_snapshot(self, s: Session, shift: _Shift, change: ExpansionChange, story_ids: set[int],
                        deleted: Deleted) -> None:
        model = scope.model_of_table(change.table_name)
        if model is None or change.before is None:
            return
        before: dict[str, Any] = dict(change.before)
        late: dict[str, Stamp] = {}
        for column in _stamp_columns(model):
            if isinstance(before.get(column), str):
                with using_calendar(None):
                    value = Stamp.parse(before[column])
                if shift.late(value):
                    assert value is not None
                    late[column] = value
        if not late:
            return
        table = f"{ExpansionChange.__tablename__}.{change.table_name}"
        if _snapshot_story(s, model, change.row_id, change.before, deleted) not in story_ids:
            shift.outside[table] += len(late)
            return
        for column, value in late.items():
            moved = shift.moved(table, change.id, column, value)
            if moved is not None:
                before[column] = moved.western_text()
        if not self.dry_run:
            change.before = before
