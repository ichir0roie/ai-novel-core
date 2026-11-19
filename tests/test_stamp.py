"""暦(`db/stamp.py` の `Calendar`)での時刻の出し入れと計算。暦は「西暦 + offset」で、offset が暦の 0 年 1 月 1 日 0 時。"""
import pytest

from data_access_logic.query.common_query import span
from db.stamp import Calendar, Stamp, StampError, using_calendar

LONG_DAY = Calendar(offset=(5000, 1, 1, 0, 0, 0), month_days=(31,) * 12, hours_per_day=27, days_per_week=7, name="長日暦")


def test_digits_round_trip_through_western_value():
    with using_calendar(LONG_DAY):
        stamp = Stamp(1592, 3, 15, 26, 30, 0)
        stored = stamp.to_int()
        assert str(Stamp.from_int(stored)) == "1592/03/15 26:30:00"
    # 中身は西暦なので、暦を立てなければ西暦の桁で見える
    assert str(Stamp.from_int(stored)) == stamp.western_text() != "1592/03/15 26:30:00"


def test_offset_is_year_zero_of_the_calendar():
    with using_calendar(LONG_DAY):
        assert Stamp(0, 1, 1).western_text() == "5000/01/01 00:00:00"
        assert str(Stamp.western(5000, 1, 1)) == "0/01/01 00:00:00"
        # 一日は地球の 27 時間
        assert Stamp(0, 1, 2).western_text() == "5000/01/02 03:00:00"


def test_order_follows_digits():
    digits = [(0, 1, 1, 0, 0, 0), (0, 1, 1, 26, 0, 0), (0, 1, 2, 0, 0, 0),
              (1592, 2, 31, 0, 0, 0), (1592, 3, 1, 0, 0, 0), (1592, 12, 31, 26, 59, 59), (1593, 1, 1, 0, 0, 0)]
    with using_calendar(LONG_DAY):
        values = [Stamp(*d).to_int() for d in digits]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_digits_are_checked_by_the_calendar():
    with using_calendar(LONG_DAY):
        with pytest.raises(StampError):
            Stamp(1592, 3, 15, 27)
        with pytest.raises(StampError):
            Stamp(1592, 13, 1)
        parsed = Stamp.parse("1592/02/31")
        assert parsed is not None and parsed.month == 2


def test_day_arithmetic_is_western_whatever_the_calendar():
    # 足し引き・隔たりはロジックなので、暦に依らず西暦の日で数える(暦は表記だけ)
    start = Stamp.western(12553, 6, 10, 22, 30)
    with using_calendar(LONG_DAY):
        moved = start.plus_days(3)
        assert start.days_until(moved) == 3
        assert start.seconds_until(moved) == 3 * 86400
    assert moved == Stamp.western(12553, 6, 13, 22, 30)


def test_span_ends_with_the_calendar():
    with using_calendar(LONG_DAY):
        assert [str(stamp) for stamp in span("1592")] == ["1592/01/01 00:00:00", "1592/12/31 26:59:59"]
        assert [str(stamp) for stamp in span("1592/03/15")] == ["1592/03/15 00:00:00", "1592/03/15 26:59:59"]
    assert [str(stamp) for stamp in span("4999")] == ["4999/01/01 00:00:00", "4999/12/31 23:59:59"]


def test_calendar_survives_json():
    assert Calendar.from_json(LONG_DAY.to_json()) == LONG_DAY
