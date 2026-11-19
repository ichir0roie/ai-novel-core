"""人物の時間の感じ方(`data_access_logic/character/time_sense.py`)。隔たりは時刻どうしで数え、人物の暦の単位で言う。"""
import pytest

from data_access_logic.character.time_sense import TimeSense
from data_access_logic.query.common_query import span
from db.stamp import Calendar, Stamp, StampError, using_calendar

LONG_DAY = Calendar(offset=(5000, 1, 1, 0, 0, 0), month_days=(31,) * 12, hours_per_day=27, days_per_week=7,
                    name="長日暦")


def test_span_picks_the_unit_that_fits_the_distance():
    with using_calendar(LONG_DAY):
        sense = TimeSense.current()
        now = Stamp(1592, 3, 15, 22)
        assert sense.ago(Stamp(1592, 3, 15, 21, 30), now) == "ついさっき"
        assert sense.ago(Stamp(1592, 3, 15, 10), now) == "12時間前"
        assert sense.ago(Stamp(1592, 3, 13, 22), now) == "2日前"
        assert sense.ago(Stamp(1592, 3, 1), now) == "2週間前"
        assert sense.ago(Stamp(1592, 1, 10), now) == "2か月前"
        assert sense.ago(Stamp(1575, 4, 1), now) == "16年前"
        # 日付だけの時刻とは、日付の差で数える
        assert sense.ago(Stamp(1592, 3, 20), now) == "5日後"
        assert sense.since(Stamp(1589, 3, 15, 22), now) == "3年前から"


def test_units_follow_the_calendar_not_the_western_days():
    with using_calendar(LONG_DAY):
        now = Stamp(1592, 3, 15, 1)
        # 暦の一日は 27 時間なので、26 時間前はまだ一日に満たない
        assert TimeSense.current().ago(Stamp(1592, 3, 14, 2), now) == "26時間前"
        # 暦の一年は 372 日なので、365 日前はまだ一年に満たない
        assert TimeSense.current().ago(Stamp(1591, 3, 22), now) == "11か月前"
    western = TimeSense(None)
    assert western.ago(Stamp.western(2026, 11, 18, 9), Stamp.western(2026, 11, 19, 8)) == "23時間前"
    # 去年の同じ日は、閏年の有る無しに関わらず一年前
    assert western.ago(Stamp.western(2025, 11, 19), Stamp.western(2026, 11, 19)) == "1年前"
    assert western.ago(Stamp.western(2026, 10, 19), Stamp.western(2026, 11, 19)) == "1か月前"
    assert western.ago(Stamp.western(2026, 10, 20), Stamp.western(2026, 11, 19)) == "4週間前"


def test_now_is_told_without_the_year():
    with using_calendar(LONG_DAY):
        told = TimeSense.current().now_for_prompt(Stamp(1592, 3, 15, 26, 30))
    assert told["日付"] == "3月15日"
    assert told["時間帯"] == "深夜"
    assert told["時刻"] == "26時ごろ"
    assert "27時間" in told["暦"] and "1592" not in str(told) and "5000" not in str(told)
    assert "暦" not in TimeSense(None).now_for_prompt(Stamp.western(2026, 11, 19, 8))


def test_day_parts_scale_with_the_length_of_the_day():
    long_day = TimeSense(LONG_DAY)
    western = TimeSense(None)
    assert western.part_of(Stamp.western(2026, 11, 19, 8)) == "朝"
    # 27 時間の一日の 9 時は、24 時間の一日の 8 時と同じ割合
    with using_calendar(LONG_DAY):
        assert long_day.part_of(Stamp(1592, 3, 15, 9)) == "朝"
        assert long_day.part_of(Stamp(1592, 3, 15, 25)) == "夜"
    # 日付だけの時刻には時間帯が無い
    assert western.part_of(Stamp.western(2026, 11, 19)) is None


def test_dates_and_years_without_a_clock_are_not_told_finer():
    western = TimeSense(None)
    now = Stamp.western(1200, 4, 1, 12)
    # 年だけ決めた時刻(1 月 1 日 0 時ちょうど)は年でだけ言う
    assert western.ago(Stamp.western(1200), now) == "今年"
    assert western.ago(Stamp.western(1199), Stamp.western(1200, 1, 3, 12)) == "1年前"
    # 日付だけ決めた時刻(0 時ちょうど)は日でまでしか言わない
    assert western.ago(Stamp.western(1200, 4, 1), now) == "今日"
    assert western.ago(Stamp.western(1200, 3, 31), now) == "昨日"
    assert western.ago(Stamp.western(1200, 3, 28), now) == "4日前"
    # 日付だけの今は、時間帯・時を言わない
    assert western.now_for_prompt(Stamp.western(1200, 4, 1)) == {"日付": "4月1日"}


def test_a_year_only_now_tells_no_date():
    assert TimeSense(None).now_for_prompt(Stamp.western(1200)) == {}


def test_period_end_uses_the_months_of_the_calendar():
    ten_months = Calendar(offset=(5000, 1, 1, 0, 0, 0), month_days=(36,) * 10, hours_per_day=24)
    with using_calendar(ten_months):
        assert [str(stamp) for stamp in span("1")] == ["1/01/01 00:00:00", "1/10/36 23:59:59"]


NOURU_LIKE = Calendar(offset=(5000, 1, 1, 0, 0, 0), month_days=(31,) * 12, hours_per_day=30, days_per_week=6,
                      minutes_per_hour=60, seconds_per_minute=54, outside_week_days=(1,) * 12, name="六日週暦")


def test_a_thirty_hour_day_with_six_day_weeks():
    assert NOURU_LIKE.day_seconds == 27 * 3600
    with using_calendar(NOURU_LIKE):
        # 一分は 54 秒まで
        assert str(Stamp(1592, 3, 15, 29, 59, 53)) == "1592/03/15 29:59:53"
        with pytest.raises(StampError):
            Stamp(1592, 3, 15, 10, 10, 54)
        sense = TimeSense.current()
        # どの月も週の 1 日目から始まり、31 日は週に数えない
        assert NOURU_LIKE.weekday((1592, 4, 1, 0, 0, 0)) == 1
        assert sense.now_for_prompt(Stamp(1592, 3, 31, 22, 30), reckoning=False) == {
            "日付": "3月31日", "週": "週に数えない日", "時間帯": "夕方", "時刻": "22時ごろ"}
        # 一時間は 54 分なので、50 分前はまだ「ついさっき」
        assert sense.ago(Stamp(1592, 3, 15, 14, 10), Stamp(1592, 3, 15, 15)) == "ついさっき"
        assert sense.ago(Stamp(1592, 3, 15, 10), Stamp(1592, 3, 15, 15)) == "5時間前"
        assert [str(stamp) for stamp in span("1592/03/15")] == ["1592/03/15 00:00:00", "1592/03/15 29:59:53"]
    assert "一分は54秒" in TimeSense.reckoning(NOURU_LIKE) and "月の終わりの1日は週に数えない" in TimeSense.reckoning(NOURU_LIKE)
