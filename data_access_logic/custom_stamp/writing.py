"""暦の行を書く(確定・修正の入口が使う)。"""
from __future__ import annotations

from collections.abc import Sequence

from data_access_logic.custom_stamp.record import CustomStampMonthRow
from data_access_logic.story.scope import calendar_of_row
from db.child_lists import replaced_rows
from db.schema import CustomStamp, CustomStampMonth
from db.stamp import Stamp, using_calendar


def write_offset(record: CustomStamp, offset: str) -> None:
    with using_calendar(None):
        stamp = Stamp.parse(offset)
    if stamp is None:
        raise ValueError("暦の始まり(offset)が空")
    record.offset = stamp


def write_months(record: CustomStamp, months: Sequence[CustomStampMonthRow]) -> None:
    rows = replaced_rows(record.months, months, CustomStampMonth)
    for number, row in enumerate(rows, start=1):
        row.number = number
    record.months = rows


def check(record: CustomStamp) -> None:
    """月・時間・始まりが暦として組めるか(始まりの時刻は、この暦の桁としても正しくなければならない)。"""
    calendar_of_row(record)
