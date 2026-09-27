from db.schema import PERSONALITY_DEFAULT, CharacterParameter, resolve_parameters
from db.stamp import Stamp


def _row(id_, start=None, end=None, **values):
    return CharacterParameter(id=id_, start=Stamp.parse(start), end=Stamp.parse(end), **values)


def test_row_without_start_and_end_covers_every_time():
    rows = [_row(1, height=140.0, sincerity="低")]
    for time in (Stamp(1), Stamp(11592), None):
        values = resolve_parameters(rows, time)
        assert values["height"] == 140.0 and values["sincerity"] == "低"


def test_period_row_overrides_only_its_own_columns_within_its_period():
    rows = [
        _row(1, height=140.0, tone="大声", sincerity="低"),
        _row(2, start="11600", height=175.0),
        _row(3, start="11610", end="11620", tone="気さく"),
    ]
    before = resolve_parameters(rows, Stamp(11599, 12, 31))
    assert (before["height"], before["tone"]) == (140.0, "大声")

    grown = resolve_parameters(rows, Stamp(11600))
    assert (grown["height"], grown["tone"], grown["sincerity"]) == (175.0, "大声", "低")

    assert resolve_parameters(rows, Stamp(11615))["tone"] == "気さく"
    # end の時刻からは効かない
    assert resolve_parameters(rows, Stamp(11620))["tone"] == "大声"


def test_without_time_only_rows_covering_every_time_apply():
    rows = [_row(1, height=140.0), _row(2, start="11600", height=175.0), _row(3, end="11500", sex="女")]
    values = resolve_parameters(rows, None)
    assert values["height"] == 140.0 and values["sex"] is None


def test_narrower_and_later_rows_win():
    rows = [
        _row(1, start="11600", end="11700", tone="二端"),
        _row(2, start="11600", tone="始まりだけ"),
        _row(3, tone="全期間"),
    ]
    assert resolve_parameters(rows, Stamp(11650))["tone"] == "二端"
    later = rows + [_row(4, start="11640", tone="遅い始まり")]
    assert resolve_parameters(later, Stamp(11650))["tone"] == "二端"
    assert resolve_parameters(later[1:], Stamp(11650))["tone"] == "遅い始まり"


def test_family_name_changes_from_its_period():
    rows = [_row(1, family_name="ベルク"), _row(2, start="11600", family_name="ロウ")]
    assert resolve_parameters(rows, Stamp(11599))["family_name"] == "ベルク"
    assert resolve_parameters(rows, Stamp(11600))["family_name"] == "ロウ"


def test_unset_personality_falls_back_to_default():
    values = resolve_parameters([_row(1, start="11600", curiosity="必")], Stamp(11500))
    assert values["curiosity"] == PERSONALITY_DEFAULT and values["tone"] is None
