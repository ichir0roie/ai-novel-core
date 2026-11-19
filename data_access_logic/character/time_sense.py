#!/usr/bin/env python3
"""人物の時間の感じ方。人物役・人物モードの人物の目に、今の時刻と物事(来歴・装い・持ち物・出来事・セリフ・思い)の古さを、
人物が数える単位で渡す。

隔たりは時刻(`Stamp`)どうしで数え、人物の暦(文脈の暦。無ければ西暦)の単位に直して、大きさに合う一つの単位で言う
(「5時間前」「3日前」「2週間前」「5か月前」「3年前」)。時間は隔たりの長さで、日は暦の日付が何度変わったかで、か月・年は
暦の上で同じ日付が何度巡ったか(去年の同じ日なら「1年前」)で数える。
年の数そのもの(西暦・暦の年)は渡さない(`character/knowledge.py` の冒頭)。

時刻は精度を持たないので、桁で見分ける。1 月 1 日 0 時ちょうどは年だけ決めた時刻(`1590`)、0 時ちょうどは日付だけ決めた時刻
(`1592/03/15`)とみなし、それより細かくは言わない(年だけなら「今年」「3年前」、日付だけなら「今日」「昨日」「3日前」)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from db.stamp import (
    Calendar, Digits, Stamp, active_calendar, western_date_number, western_month_number,
)

_HOUR_SECONDS = 3600
_WESTERN_MONTHS = 12

# 時刻の精度。桁で見分ける
_YEAR, _DATE, _CLOCK = 0, 1, 2

# 一日のうちの時間帯と、その終わり。一日を 24 に割った刻みで書き、一日の長さが違う暦でも同じ割合で区切る
_DAY_PARTS = ((4, "深夜"), (6, "明け方"), (10, "朝"), (12, "昼前"), (14, "昼"), (17, "午後"), (19, "夕方"), (23, "夜"),
              (24, "深夜"))


def _precision(digits: Digits) -> int:
    if digits[3:] != (0, 0, 0):
        return _CLOCK
    return _YEAR if digits[1:3] == (1, 1) else _DATE


@dataclass(frozen=True)
class TimeSense:
    # 人物が数える暦。None なら西暦
    calendar: Calendar | None = None

    @classmethod
    def current(cls) -> TimeSense:
        """文脈の暦で数える感じ方。"""
        return cls(active_calendar())

    @property
    def hours_per_day(self) -> int:
        return 24 if self.calendar is None else self.calendar.hours_per_day

    @property
    def days_per_week(self) -> int:
        return 7 if self.calendar is None else self.calendar.days_per_week

    @property
    def months_per_year(self) -> int:
        return _WESTERN_MONTHS if self.calendar is None else len(self.calendar.month_days)

    def _digits(self, stamp: Stamp) -> Digits:
        western = stamp.western_digits
        return western if self.calendar is None else self.calendar.to_local(western)

    def _date_number(self, digits: Digits) -> int:
        return western_date_number(digits) if self.calendar is None else self.calendar.date_number(digits)

    def _month_number(self, digits: Digits) -> int:
        return western_month_number(digits) if self.calendar is None else self.calendar.month_number(digits)

    @property
    def _hour_seconds(self) -> int:
        return _HOUR_SECONDS if self.calendar is None else self.calendar.hour_seconds

    @property
    def _minutes_per_hour(self) -> int:
        return 60 if self.calendar is None else self.calendar.minutes_per_hour

    @staticmethod
    def _borrow(start: Digits, end: Digits, first: int, last: int) -> int:
        """後の桁(`first` から `last` の手前まで)がまだ巡っていなければ 1。"""
        return 1 if end[first:last] < start[first:last] else 0

    def _days(self, start: Digits, end: Digits, compared: int) -> int:
        """暦の日付が何度変わったか。時刻まで見るなら、時刻がまだ巡っていない分を引く。"""
        return self._date_number(end) - self._date_number(start) - self._borrow(start, end, 3, compared)

    def days(self, earlier: Stamp, later: Stamp) -> int:
        """`earlier` から `later` までの、まるごとの日数(暦の日付と時刻で数える)。"""
        return self._days(self._digits(earlier), self._digits(later), 6)

    def _span(self, earlier: Stamp, later: Stamp) -> tuple[int, str | None]:
        """隔たりの精度と、大きさに合う一つの単位で言った隔たり(端数は切り捨てる)。精度の一番小さい単位に満たなければ None。"""
        start, end = self._digits(earlier), self._digits(later)
        precision = min(_precision(start), _precision(end))
        if precision == _YEAR:
            years = end[0] - start[0]
            return precision, f"{years}年" if years >= 1 else None
        compared = 3 if precision == _DATE else 6
        days = self._days(start, end, compared)
        if precision == _CLOCK:
            seconds = earlier.seconds_until(later)
            hour = self._hour_seconds
            if seconds < hour:
                return precision, None
            if days < 1:
                return precision, f"{seconds // hour}時間"
        elif days < 1:
            return precision, None
        week = self.days_per_week
        if days < week:
            return precision, f"{days}日"
        years = end[0] - start[0] - self._borrow(start, end, 1, compared)
        if years >= 1:
            return precision, f"{years}年"
        months = self._month_number(end) - self._month_number(start) - self._borrow(start, end, 2, compared)
        if months >= 1:
            return precision, f"{months}か月"
        return precision, f"{days // week}週間"

    def span(self, earlier: Stamp, later: Stamp) -> str | None:
        """`earlier` から `later` までの隔たり(「3日」)。精度の一番小さい単位(時間・日・年)に満たなければ None。"""
        return self._span(earlier, later)[1]

    def ago(self, start: Stamp, now: Stamp) -> str:
        """`start` が `now` からどれほど前か(「3日前」)。後なら「3日後」。"""
        past = start.seconds_until(now) >= 0
        precision, span = self._span(start, now) if past else self._span(now, start)
        if span is None:
            return {_YEAR: "今年", _DATE: "今日", _CLOCK: "ついさっき" if past else "まもなく"}[precision]
        if precision == _DATE and span == "1日":
            return "昨日" if past else "明日"
        return f"{span}{'前' if past else '後'}"

    def since(self, start: Stamp, now: Stamp) -> str:
        """`start` から今まで続いていること(「3年前から」)。物の古さ・思いの長さに使う。"""
        return f"{self.ago(start, now)}から"

    def part_of(self, stamp: Stamp) -> str | None:
        """その時刻の時間帯(日付だけ・年だけの時刻なら None)。語り部の材料に、人物が受け取るのと同じ時間帯を添えるのに使う。"""
        digits = self._digits(stamp)
        if _precision(digits) != _CLOCK:
            return None
        return self._part_of_day(digits)

    def _part_of_day(self, digits: Digits) -> str:
        position = (digits[3] + digits[4] / self._minutes_per_hour) * 24 / self.hours_per_day
        return next(name for end, name in _DAY_PARTS if position < end)

    def now_for_prompt(self, now: Stamp, reckoning: bool = True) -> dict[str, Any]:
        """今の時刻を、年を抜いて月日・時間帯・時で言う(日付だけの時刻なら月日だけ、年だけの時刻なら言わない)。暦が西暦でなければ、
        週の何日目かと、一日・一年の長さを添える(`reckoning`)。"""
        digits = self._digits(now)
        _, month, day, hour, _, _ = digits
        names = () if self.calendar is None else self.calendar.month_names
        named = names[month - 1] if month <= len(names) else ""
        # 年だけ決めた時刻(1 月 1 日 0 時ちょうど)は、月日も言わない
        told: dict[str, Any] = {} if _precision(digits) == _YEAR else {"日付": f"{named or f'{month}月'}{day}日"}
        if self.calendar is not None and _precision(digits) != _YEAR:
            weekday = self.calendar.weekday(digits)
            told["週"] = "週に数えない日" if weekday is None else f"週の{weekday}日目"
        if _precision(digits) == _CLOCK:
            told["時間帯"] = self._part_of_day(digits)
            told["時刻"] = f"{hour}時ごろ"
        if reckoning and self.calendar is not None:
            told["暦"] = self.reckoning(self.calendar)
        return told

    @staticmethod
    def reckoning(calendar: Calendar) -> str:
        """暦の一日・一週・一年の長さ(年の数と始まりは言わない)。"""
        days = calendar.month_days
        months = f"どの月も{days[0]}日" if len(set(days)) == 1 else "月の日数は順に" + "・".join(map(str, days))
        clock = ("" if (calendar.minutes_per_hour, calendar.seconds_per_minute) == (60, 60)
                 else f"・一時間は{calendar.minutes_per_hour}分・一分は{calendar.seconds_per_minute}秒")
        outside = calendar.outside_week_days
        weeks = ("" if not any(outside) else
                 f"。月の終わりの{outside[0]}日は週に数えない" if len(set(outside)) == 1 else
                 "。月の終わりの何日か(月ごとに順に" + "・".join(map(str, outside)) + "日)は週に数えない")
        return (f"一日は{calendar.hours_per_day}時間(0〜{calendar.hours_per_day - 1}時){clock}、一週は{calendar.days_per_week}日、"
                f"一年は{len(days)}か月・{calendar.year_days}日({months}){weeks}")
