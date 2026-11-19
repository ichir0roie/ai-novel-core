#!/usr/bin/env python3
"""作中の時刻。暦は西暦の続きで万の位に乗る年も出る(`43600712`、`999990101000000`)ので、
9999 年までしか持てない `datetime` は使わず、年・月・日・時・分・秒をそのまま持つ。

db には西暦の桁を並べた整数(`年*10^10 + 月*10^8 + … + 秒`)で入れるので、大小がそのまま時の前後になる。

作品が西暦でない暦(`custom_stamp`)を持つときは、その暦を文脈(`using_calendar`)に立てる。暦は表記だけに効く:
桁(`year` など)・文字列での出し入れ(`str` / `parse`)・桁からの組み立て(`Stamp(年, 月, …)`)・表記で指した期間の終わり
(`period_end`)を文脈の暦で数える。前後・隔たり・日数の足し引き(`days_until` / `plus_days` / `seconds_until`)は暦に依らず
西暦の時刻で数える。人物が隔たりをどう感じるかは `data_access_logic/character/time_sense.py`。
"""
from __future__ import annotations

import datetime as _datetime
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import total_ordering

_DIGITS = re.compile(r"\A\d+\Z")

# 月ごとの日数(平年)と、グレゴリオ暦の四百年の日数
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DAYS_IN_400_YEARS = 146097
_WESTERN_DAY_SECONDS = 86400

# 年・月・日・時・分・秒
Digits = tuple[int, int, int, int, int, int]
_WESTERN_MONTHS = 12


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        return 29
    return _MONTH_DAYS[month - 1]


def _days_before_year(year: int) -> int:
    y = year - 1
    return 365 * y + y // 4 - y // 100 + y // 400


def _ordinal(year: int, month: int, day: int) -> int:
    """1 年 1 月 1 日を 1 とする通算日。"""
    return _days_before_year(year) + sum(_days_in_month(year, m) for m in range(1, month)) + day


def _from_ordinal(ordinal: int) -> tuple[int, int, int]:
    year = ordinal * 400 // _DAYS_IN_400_YEARS + 1
    while _days_before_year(year) >= ordinal:
        year -= 1
    while _days_before_year(year + 1) < ordinal:
        year += 1
    day = ordinal - _days_before_year(year)
    month = 1
    while day > _days_in_month(year, month):
        day -= _days_in_month(year, month)
        month += 1
    return year, month, day


def _clock_seconds(digits: Digits) -> int:
    return digits[3] * 3600 + digits[4] * 60 + digits[5]


def western_date_number(digits: Digits) -> int:
    """西暦の日付の通し番号(1 年 1 月 1 日が 1。時刻は見ない)。"""
    return _ordinal(*digits[:3])


def western_month_number(digits: Digits) -> int:
    return digits[0] * _WESTERN_MONTHS + digits[1]


def _western_seconds(digits: Digits) -> int:
    return (_ordinal(*digits[:3]) - 1) * _WESTERN_DAY_SECONDS + _clock_seconds(digits)


def _western_digits(seconds: int) -> Digits:
    days, rest = divmod(seconds, _WESTERN_DAY_SECONDS)
    hour, rest = divmod(rest, 3600)
    minute, second = divmod(rest, 60)
    return (*_from_ordinal(days + 1), hour, minute, second)


class StampError(ValueError):
    pass


def _check_western(digits: Digits) -> Digits:
    _, month, day, hour, minute, second = digits
    if not 1 <= month <= 12:
        raise StampError(f"月が 1〜12 でない: {month}")
    if not 1 <= day <= 31:
        raise StampError(f"日が 1〜31 でない: {day}")
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
        raise StampError(f"時刻の桁が範囲の外: {_text(digits)}")
    return digits


def _text(digits: Digits) -> str:
    year, month, day, hour, minute, second = digits
    return f"{year}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


@dataclass(frozen=True)
class Calendar:
    """西暦でない暦(`db/schema.py` の `CustomStamp`)。`offset` より前は西暦で数え、`offset` から先はこの暦で数える。

    `offset` の時刻の桁は、西暦でもこの暦でも同じ(年の数は西暦から続く)。秒は地球の秒のままで、一分の秒の数・一時間の分の数・
    一日の時間の数は暦ごとに決める(一日 30 時間・一時間 60 分・一分 54 秒なら、一日は地球の 27 時間)。
    月の終わりの何日か(`outside_week_days`)は週に数えない日にできる(週は月の頭から数え直さず、週に数える日だけで続く)。
    """

    offset: Digits
    month_days: tuple[int, ...]
    hours_per_day: int = 24
    days_per_week: int = 7
    name: str = ""
    # 月の呼び名(空の月は数で呼ぶ)
    month_names: tuple[str, ...] = ()
    minutes_per_hour: int = 60
    seconds_per_minute: int = 60
    # 月ごとの、月の終わりの週に数えない日の数(空なら、どの日も週に数える)
    outside_week_days: tuple[int, ...] = ()
    year_days: int = field(init=False)
    hour_seconds: int = field(init=False)
    day_seconds: int = field(init=False)

    def __post_init__(self) -> None:
        if not self.month_days or any(days < 1 for days in self.month_days):
            raise StampError(f"暦の月の日数が足りない: {self.month_days}")
        if min(self.hours_per_day, self.days_per_week, self.minutes_per_hour, self.seconds_per_minute) < 1:
            raise StampError("暦の一日の時間・一週の日数・一時間の分・一分の秒が 1 より小さい")
        outside = self.outside_week_days
        if outside and (len(outside) != len(self.month_days)
                        or any(not 0 <= extra < days for extra, days in zip(outside, self.month_days))):
            raise StampError(f"週に数えない日の数が、月ごとに 0〜その月の日数未満でない: {outside}")
        object.__setattr__(self, "year_days", sum(self.month_days))
        object.__setattr__(self, "hour_seconds", self.minutes_per_hour * self.seconds_per_minute)
        object.__setattr__(self, "day_seconds", self.hours_per_day * self.hour_seconds)
        self.check(self.offset)

    def check(self, digits: Digits) -> Digits:
        """この暦の桁として正しいか。"""
        _, month, day, hour, minute, second = digits
        if not 1 <= month <= len(self.month_days):
            raise StampError(f"月が 1〜{len(self.month_days)} でない: {month}")
        if not 1 <= day <= self.month_days[month - 1]:
            raise StampError(f"{month} 月の日が 1〜{self.month_days[month - 1]} でない: {day}")
        if not (0 <= hour < self.hours_per_day and 0 <= minute < self.minutes_per_hour
                and 0 <= second < self.seconds_per_minute):
            raise StampError(f"時刻の桁が範囲の外(一日は {self.hours_per_day} 時間・一時間は {self.minutes_per_hour} 分・"
                             f"一分は {self.seconds_per_minute} 秒): {_text(digits)}")
        return digits

    def _clock_seconds(self, digits: Digits) -> int:
        return digits[3] * self.hour_seconds + digits[4] * self.seconds_per_minute + digits[5]

    def _day_number(self, digits: Digits) -> int:
        year, month, day = digits[:3]
        return year * self.year_days + sum(self.month_days[:month - 1]) + day - 1

    def _seconds(self, digits: Digits) -> int:
        return self._day_number(digits) * self.day_seconds + self._clock_seconds(digits)

    def _digits(self, seconds: int) -> Digits:
        days, rest = divmod(seconds, self.day_seconds)
        year, day = divmod(days, self.year_days)
        month = 1
        while day >= self.month_days[month - 1]:
            day -= self.month_days[month - 1]
            month += 1
        hour, rest = divmod(rest, self.hour_seconds)
        minute, second = divmod(rest, self.seconds_per_minute)
        return year, month, day + 1, hour, minute, second

    def to_western(self, digits: Digits) -> Digits:
        """この暦の桁を、西暦の桁に。`offset` より前の桁は西暦のまま読む。"""
        if digits < self.offset:
            return _check_western(digits)
        self.check(digits)
        seconds = _western_seconds(self.offset) + self._seconds(digits) - self._seconds(self.offset)
        return _western_digits(seconds)

    def to_local(self, western: Digits) -> Digits:
        """西暦の桁を、この暦の桁に。`offset` より前は西暦のまま。"""
        if western < self.offset:
            return western
        return self._digits(self._seconds(self.offset) + _western_seconds(western) - _western_seconds(self.offset))

    def from_western_clock(self, digits: Digits) -> Digits:
        """西暦の一日(24 時間)のつもりで書いた桁を、日付を保ち、一日のうちの割合を保ってこの暦の桁にする
        (西暦の 12 時は、一日 30 時間の暦の 15 時)。分に丸め、0 時ちょうどは 0 時ちょうどのまま。"""
        minutes = round(_clock_seconds(digits) / _WESTERN_DAY_SECONDS * self.day_seconds / self.seconds_per_minute)
        minutes = min(minutes, self.hours_per_day * self.minutes_per_hour - 1)
        hour, minute = divmod(minutes, self.minutes_per_hour)
        return (*digits[:3], hour, minute, 0)

    def date_number(self, local: Digits) -> int:
        """`offset` の日を 0 とする日付の通し番号(時刻は見ない)。始まりより前は西暦の日で数える。"""
        if local < self.offset:
            return _ordinal(*local[:3]) - _ordinal(*self.offset[:3])
        return self._day_number(local) - self._day_number(self.offset)

    def month_number(self, local: Digits) -> int:
        """`offset` の月を 0 とする月の通し番号。始まりより前は西暦の 12 か月で数える。"""
        months = _WESTERN_MONTHS if local < self.offset else len(self.month_days)
        return (local[0] - self.offset[0]) * months + local[1] - self.offset[1]

    def hours_at(self, local: Digits) -> int:
        """その時刻の一日の時間の数。始まりより前は西暦の 24 時間。"""
        return 24 if local < self.offset else self.hours_per_day

    def hour_seconds_at(self, local: Digits) -> int:
        """その時刻の一時間の秒の数。始まりより前は西暦の 3600 秒。"""
        return 3600 if local < self.offset else self.hour_seconds

    def minutes_at(self, local: Digits) -> int:
        return 60 if local < self.offset else self.minutes_per_hour

    def _week_days_of(self, month: int) -> int:
        """その月の週に数える日の数。"""
        return self.month_days[month - 1] - (self.outside_week_days[month - 1] if self.outside_week_days else 0)

    def _week_count(self, local: Digits) -> int:
        """その日より前に週に数えた日の数(年をまたいで続けて数える)。"""
        year, month, day = local[:3]
        per_year = sum(self._week_days_of(m) for m in range(1, len(self.month_days) + 1))
        before = sum(self._week_days_of(m) for m in range(1, month))
        return year * per_year + before + min(day - 1, self._week_days_of(month))

    def weekday(self, local: Digits) -> int | None:
        """週の何日目か(暦の始まりの日を 1 日目とする)。週に数えない日・始まりより前なら None。"""
        if local < self.offset or local[2] > self._week_days_of(local[1]):
            return None
        return (self._week_count(local) - self._week_count(self.offset)) % self.days_per_week + 1

    def to_json(self) -> dict:
        return {"name": self.name, "offset": _text(self.offset), "month_days": list(self.month_days),
                "hours_per_day": self.hours_per_day, "days_per_week": self.days_per_week,
                "month_names": list(self.month_names), "minutes_per_hour": self.minutes_per_hour,
                "seconds_per_minute": self.seconds_per_minute, "outside_week_days": list(self.outside_week_days)}

    @classmethod
    def from_json(cls, value: dict) -> "Calendar":
        offset = _parse_digits(value["offset"])
        if offset is None:
            raise StampError("暦のオフセットが空")
        return cls(offset=offset, month_days=tuple(int(days) for days in value["month_days"]),
                   hours_per_day=int(value["hours_per_day"]), days_per_week=int(value["days_per_week"]),
                   name=str(value.get("name") or ""),
                   month_names=tuple(str(name or "") for name in value.get("month_names") or ()),
                   minutes_per_hour=int(value.get("minutes_per_hour") or 60),
                   seconds_per_minute=int(value.get("seconds_per_minute") or 60),
                   outside_week_days=tuple(int(days) for days in value.get("outside_week_days") or ()))


def _filled(prefix: Sequence[int], last_month: int, last_day: Callable[[int], int], last_clock: tuple[int, int, int],
            ) -> Digits:
    digits = list(prefix[:6])
    if len(digits) < 2:
        digits.append(last_month)
    if len(digits) < 3:
        digits.append(last_day(digits[1]))
    digits += list(last_clock)[len(digits) - 3:]
    return tuple(digits)  # type: ignore[return-value]


def period_end(prefix: Sequence[int]) -> "Stamp":
    """桁の頭(年だけ・年月・年月日…)で指した期間の、最後の時刻。文脈の暦の月の数・月の日数・一日の時間・一時間の分・一分の秒で数える。"""
    calendar = active_calendar()
    # 始まりより前の期間と、暦に無い月は西暦で埋める(暦の月の数が西暦より少ないこともある)
    if (calendar is not None and tuple(prefix) >= calendar.offset[:len(prefix)]
            and (len(prefix) < 2 or 1 <= prefix[1] <= len(calendar.month_days))):
        months = calendar.month_days
        local = _filled(prefix, len(months), lambda month: months[month - 1],
                        (calendar.hours_per_day - 1, calendar.minutes_per_hour - 1, calendar.seconds_per_minute - 1))
        if local >= calendar.offset:
            return Stamp(*local)
    return Stamp(*_filled(prefix, _WESTERN_MONTHS, lambda month: _days_in_month(prefix[0], month), (23, 59, 59)))


def _western_plus_days(western: Digits, days: int) -> Digits:
    return (*_from_ordinal(_ordinal(*western[:3]) + days), *western[3:])


_calendar: ContextVar[Calendar | None] = ContextVar("calendar", default=None)


def active_calendar() -> Calendar | None:
    """文脈の暦。None なら西暦。"""
    return _calendar.get()


def set_calendar(calendar: Calendar | None) -> None:
    """今の文脈に暦を立てたままにする(`db/story_scope.py` の `adopt`)。"""
    _calendar.set(calendar)


@contextmanager
def using_calendar(calendar: Calendar | None) -> Iterator[Calendar | None]:
    token = _calendar.set(calendar)
    try:
        yield calendar
    finally:
        _calendar.reset(token)


def _parse_digits(value: str) -> Digits | None:
    text = value.strip()
    if not text:
        return None
    if _DIGITS.match(text):
        if len(text) > 6:
            raise StampError(
                f"年として長すぎる: {text}。"
                f"日付まで書くなら y/mm/dd hh:mm:ss の形にする")
        return int(text), 1, 1, 0, 0, 0
    parts = [p for p in re.split(r"[-/ :T]", text) if p != ""]
    if not parts or not all(p.isdigit() for p in parts):
        raise StampError(f"時刻として読めない: {value!r}")
    numbers = [int(p) for p in parts[:6]]
    defaults = [1, 1, 1, 0, 0, 0]
    return tuple(numbers + defaults[len(numbers):])  # type: ignore[return-value]


@total_ordering
class Stamp:
    # 中身は西暦の桁。文脈の暦で数えた桁は、暦ごとに一度だけ数えて `_local` に控える
    __slots__ = ("_western", "_local")

    def __init__(self, year, month=1, day=1, hour=0, minute=0, second=0):
        """文脈の暦の桁から組み立てる。"""
        digits: Digits = (int(year), int(month), int(day), int(hour), int(minute), int(second))
        calendar = active_calendar()
        self._western = _check_western(digits) if calendar is None else calendar.to_western(digits)
        self._local: tuple[Calendar | None, Digits] | None = None

    @classmethod
    def western(cls, year, month=1, day=1, hour=0, minute=0, second=0) -> "Stamp":
        """文脈の暦に関わらず、西暦の桁から組み立てる。"""
        with using_calendar(None):
            return cls(year, month, day, hour, minute, second)

    @classmethod
    def _of_western(cls, digits: Digits) -> "Stamp":
        stamp = cls.__new__(cls)
        stamp._western = digits
        stamp._local = None
        return stamp

    @property
    def western_digits(self) -> Digits:
        return self._western

    @property
    def digits(self) -> Digits:
        """文脈の暦で数えた桁。"""
        calendar = active_calendar()
        if self._local is None or self._local[0] is not calendar:
            self._local = (calendar, self._western if calendar is None else calendar.to_local(self._western))
        return self._local[1]

    @property
    def year(self) -> int:
        return self.digits[0]

    @property
    def month(self) -> int:
        return self.digits[1]

    @property
    def day(self) -> int:
        return self.digits[2]

    @property
    def hour(self) -> int:
        return self.digits[3]

    @property
    def minute(self) -> int:
        return self.digits[4]

    @property
    def second(self) -> int:
        return self.digits[5]

    @classmethod
    def parse(cls, value) -> "Stamp | None":
        """文字列は文脈の暦の桁として読む。"""
        if value is None:
            return None
        if isinstance(value, Stamp):
            return value
        if isinstance(value, _datetime.datetime):
            return cls.western(value.year, value.month, value.day, value.hour, value.minute, value.second)
        if isinstance(value, _datetime.date):
            return cls.western(value.year, value.month, value.day)
        digits = _parse_digits(str(value))
        return None if digits is None else cls(*digits)

    @classmethod
    def from_int(cls, value) -> "Stamp | None":
        """db の列の整数(西暦の桁)から。"""
        if value is None:
            return None
        value = int(value)
        rest, second = divmod(value, 100)
        rest, minute = divmod(rest, 100)
        rest, hour = divmod(rest, 100)
        rest, day = divmod(rest, 100)
        year, month = divmod(rest, 100)
        return cls._of_western(_check_western((year, month, day, hour, minute, second)))

    def to_int(self) -> int:
        year, month, day, hour, minute, second = self._western
        return (((((year * 100 + month) * 100 + day) * 100
                  + hour) * 100 + minute) * 100 + second)

    def western_text(self) -> str:
        """西暦で数えた文字列(暦のある作品で、西暦と並べて出すとき)。"""
        return _text(self._western)

    def __str__(self) -> str:
        return _text(self.digits)

    def __repr__(self) -> str:
        return f"Stamp({self.western_text()})"

    # pydantic のモデルの欄に置けるようにする。JSON では `__str__` の文字列で行き来する(API で材料を運ぶため)
    @classmethod
    def __get_pydantic_core_schema__(cls, _source, _handler):
        from pydantic_core import core_schema

        return core_schema.no_info_plain_validator_function(
            cls._validated,
            serialization=core_schema.plain_serializer_function_ser_schema(str, when_used="json"))

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema, _handler):
        return {"type": "string"}

    @classmethod
    def _validated(cls, value) -> "Stamp":
        stamp = cls.parse(value)
        if stamp is None:
            raise ValueError("時刻が空")
        return stamp

    def days_until(self, other: "Stamp") -> int:
        """`other` までの日数(時刻は見ない)。`other` が前なら負。暦に依らず西暦の日で数える。"""
        return _ordinal(*other._western[:3]) - _ordinal(*self._western[:3])

    def plus_days(self, days: int) -> "Stamp":
        """`days` 日後。月末・閏年をまたいで数え、時・分・秒はそのまま。暦に依らず西暦の日で数える。"""
        return Stamp._of_western(_western_plus_days(self._western, days))

    def seconds_until(self, other: "Stamp") -> int:
        """`other` までの秒。`other` が前なら負。暦に依らない時刻の隔たり。"""
        return _western_seconds(other._western) - _western_seconds(self._western)

    def __eq__(self, other) -> bool:
        return isinstance(other, Stamp) and self._western == other._western

    def __lt__(self, other) -> bool:
        if not isinstance(other, Stamp):
            return NotImplemented
        return self._western < other._western

    def __hash__(self) -> int:
        return hash(self._western)
