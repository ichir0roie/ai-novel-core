#!/usr/bin/env python3
"""python の `datetime` は 9999 年までしか持てないので使わない。

作中の暦は西暦の続きで、万の位に乗る年も出る(`43600712`、`999990101000000`)。
`datetime` はそこで `year is out of range` と言って止まるため、
ここでは年・月・日・時・分・秒をそのまま持つ小さな値として扱う。

台帳には整数として入れる(`年*10^10 + 月*10^8 + … + 秒`)。
桁を並べただけなので、大小がそのまま時の前後になる。
"""
from __future__ import annotations

import datetime as _datetime
import re
from functools import total_ordering

_DIGITS = re.compile(r"\A\d+\Z")

# 年の下に付く五つの欄。桁数と、書かれなかったときの値
_PARTS = (("month", 2, 1), ("day", 2, 1),
          ("hour", 2, 0), ("minute", 2, 0), ("second", 2, 0))

# 年より下の桁の合計。10 桁(mmddhhmmss)
_UNDER = sum(width for _, width, _ in _PARTS)


class StampError(ValueError):
    pass


@total_ordering
class Stamp:
    __slots__ = ("year", "month", "day", "hour", "minute", "second")

    def __init__(self, year, month=1, day=1, hour=0, minute=0, second=0):
        self.year = int(year)
        self.month = int(month)
        self.day = int(day)
        self.hour = int(hour)
        self.minute = int(minute)
        self.second = int(second)
        if not 1 <= self.month <= 12:
            raise StampError(f"月が 1〜12 でない: {self.month}")
        if not 1 <= self.day <= 31:
            raise StampError(f"日が 1〜31 でない: {self.day}")
        if not (0 <= self.hour < 24 and 0 <= self.minute < 60
                and 0 <= self.second < 60):
            raise StampError(f"時刻の桁が範囲の外: {self}")

    # --- 作る -----------------------------------------------------------

    @classmethod
    def parse(cls, value) -> "Stamp | None":
        if value is None or value == "":
            return None
        if isinstance(value, Stamp):
            return value
        if isinstance(value, _datetime.datetime):
            return cls(value.year, value.month, value.day,
                       value.hour, value.minute, value.second)
        if isinstance(value, _datetime.date):
            return cls(value.year, value.month, value.day)

        text = str(value).strip()
        if not text:
            return None

        if _DIGITS.match(text):
            if len(text) > 6:
                raise StampError(
                    f"年として長すぎる: {text}。"
                    f"日付まで書くなら y/mm/dd hh:mm:ss の形にする")
            return cls(int(text))

        parts = [p for p in re.split(r"[-/ :T]", text) if p != ""]
        if not parts or not all(p.isdigit() for p in parts):
            raise StampError(f"時刻として読めない: {value!r}")
        nums = [int(p) for p in parts[:6]]
        return cls(*nums)

    @classmethod
    def from_int(cls, value) -> "Stamp | None":
        if value is None:
            return None
        value = int(value)
        rest, second = divmod(value, 100)
        rest, minute = divmod(rest, 100)
        rest, hour = divmod(rest, 100)
        rest, day = divmod(rest, 100)
        year, month = divmod(rest, 100)
        return cls(year, month, day, hour, minute, second)

    # --- 出す -----------------------------------------------------------

    def to_int(self) -> int:
        return (((((self.year * 100 + self.month) * 100 + self.day) * 100
                  + self.hour) * 100 + self.minute) * 100 + self.second)

    def __str__(self) -> str:
        return (f"{self.year}/{self.month:02d}/{self.day:02d} "
                f"{self.hour:02d}:{self.minute:02d}:{self.second:02d}")

    def __repr__(self) -> str:
        return f"Stamp({self})"

    # --- 比べる ---------------------------------------------------------

    def __eq__(self, other) -> bool:
        return isinstance(other, Stamp) and self.to_int() == other.to_int()

    def __lt__(self, other) -> bool:
        if not isinstance(other, Stamp):
            return NotImplemented
        return self.to_int() < other.to_int()

    def __hash__(self) -> int:
        return hash(self.to_int())
