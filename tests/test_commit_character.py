import json

import pytest

from ai.claude_code.interface._base import UnknownFieldError
from ai.claude_code.interface.randomizer.commit_character import CommitCharacter
from ai.claude_code.interface.randomizer.commit_place import CommitPlace
from ai.claude_code.interface.randomizer.create_random_character import CreateRandomCharacter
from ai.claude_code.interface.randomizer.update_character import UpdateCharacter
from ai.claude_code.interface.story.update_story import UpdateStory
from ai.claude_code.interface.story.read_character import ReadCharacter
from db.schema import (
    PERSONALITY_COLUMNS, PERSONALITY_LEVELS, Character, CharacterHistory, CharacterPlace, ConfirmStatus,
    Location, Story,
)
from db.stamp import Stamp
from randomizer.random_character_generator import build_parameter


@pytest.fixture
def world(session):
    root = Location(name="世界", kind="世界", text="")
    session.add(root)
    session.flush()
    village = Location(name="村", kind="村", text="", parent_id=root.id,
                       start=Stamp(2100), end=Stamp(2200))
    session.add(village)
    session.flush()
    session.add(Story(name="世界の話", place_id=root.id, text="世界の筋書き", narration="", state="構想中"))
    session.add(Story(name="村の話", place_id=village.id, text="村の筋書き", narration="", state="構想中"))
    session.commit()
    return {"root": root.id, "village": village.id}


def _draft(parameter: dict | None = None, **overrides) -> str:
    draft = CreateRandomCharacter().run()
    draft["parameters"][0].update(parameter or {})
    draft.update(overrides)
    return json.dumps(draft, ensure_ascii=False)


def test_commit_from_json_string(session, world):
    result = CommitCharacter(_draft(place_id=world["root"], start="2100", end="2160")).run()

    record = session.get(Character, result["id"])
    assert record.start == Stamp(2100) and record.end == Stamp(2160)
    [row] = record.parameters
    # 誕生・死亡は列を持たず、この唯一の行の start / end がそれを兼ねる
    assert row.start == Stamp(2100) and row.end == Stamp(2160)
    assert all(getattr(row, name) in PERSONALITY_LEVELS for name in PERSONALITY_COLUMNS)
    [parameter] = result["parameters"]
    assert {name: parameter[name] for name in PERSONALITY_COLUMNS} == {
        name: getattr(row, name) for name in PERSONALITY_COLUMNS}

    place = session.query(CharacterPlace).filter_by(character_id=record.id).one()
    assert place.location_id == world["root"]
    assert place.start == Stamp(2100)


def test_committed_character_defaults_to_approved(session, world):
    result = CommitCharacter(_draft(place_id=world["root"], start="2100")).run()
    assert session.get(Character, result["id"]).confirmed == ConfirmStatus.APPROVED


def test_committed_character_confirmed_can_be_overridden(session, world):
    result = CommitCharacter(
        _draft(place_id=world["root"], start="2100", confirmed=ConfirmStatus.PENDING)).run()
    assert session.get(Character, result["id"]).confirmed == ConfirmStatus.PENDING


def test_committed_character_is_a_sub_character_by_default(session, world):
    result = CommitCharacter(_draft(place_id=world["root"], start="2100")).run()

    assert session.get(Character, result["id"]).main_character is False


def test_commit_rejects_non_level_personality(session, world):
    with pytest.raises(ValueError, match="無/低/並/高/必"):
        CommitCharacter(_draft({"sincerity": 0}, place_id=world["root"], start="2100")).run()
    assert session.query(Character).count() == 0


def test_commit_rejects_unknown_field(world):
    with pytest.raises(UnknownFieldError):
        CommitCharacter(_draft(place_id=world["root"], start="2100", charisma="高")).run()
    # 期間ごとの欄は parameters の中にしか置けない
    with pytest.raises(UnknownFieldError):
        CommitCharacter(_draft(place_id=world["root"], start="2100", sincerity="高")).run()
    with pytest.raises(ValueError, match="スキーマに無い欄"):
        CommitCharacter(_draft({"charisma": "高"}, place_id=world["root"], start="2100")).run()


def test_commit_requires_story_on_place(session):
    lonely = Location(name="孤島", kind="島", text="")
    session.add(lonely)
    session.commit()
    with pytest.raises(ValueError, match="作品が無い"):
        CommitCharacter(_draft(place_id=lonely.id, start="2100")).run()


def test_no_character_cap_per_place(session, world):
    for _ in range(7):
        CommitCharacter(_draft(place_id=world["village"], start="2101", end="2150")).run()
    assert session.query(CharacterPlace).filter_by(location_id=world["village"]).count() == 7


@pytest.mark.parametrize("start, end, message", [
    ("2300", None, "end=2200/01/01 00:00:00 以後"),
    ("2150", "2250", "end=2200/01/01 00:00:00 を超える"),
    ("2050", "2150", "start=2100/01/01 00:00:00 より前"),
])
def test_commit_rejects_span_outside_parent(session, world, start, end, message):
    with pytest.raises(ValueError, match=message):
        CommitCharacter(_draft(place_id=world["village"], start=start, end=end)).run()
    assert session.query(Character).count() == 0


@pytest.mark.parametrize("start, end", [
    ("2100", "2200"),
    ("2150", "2190"),
    ("2150", None),
    (None, None),
])
def test_commit_accepts_span_inside_parent(world, start, end):
    result = CommitCharacter(_draft(place_id=world["village"], start=start, end=end)).run()
    assert result["id"] is not None


def test_commit_without_parent_span_accepts_any_time(world):
    result = CommitCharacter(_draft(place_id=world["root"], start="1", end="9999")).run()
    assert result["start"] == "1/01/01 00:00:00"


def test_update_personality(session, world):
    committed = CommitCharacter(_draft(place_id=world["root"], start="2100")).run()
    [base] = committed["parameters"]
    base_id = session.get(Character, committed["id"]).parameters[0].id

    parameters = [dict(base, curiosity="必"), build_parameter(start="2120", curiosity="低")]
    updated = UpdateCharacter({"id": committed["id"], "parameters": parameters}).run()
    assert [row["curiosity"] for row in updated["parameters"]] == ["必", "低"]
    session.expire_all()
    record = session.get(Character, committed["id"])
    # 同じ位置の行は使い回す
    assert record.parameters[0].id == base_id
    assert record.parameters_at(Stamp(2110))["curiosity"] == "必"
    assert record.parameters_at(Stamp(2130))["curiosity"] == "低"

    for bad in ({"curiosity": 3}, {"sincerity": "中"}):
        with pytest.raises(ValueError, match="無/低/並/高/必"):
            UpdateCharacter({"id": committed["id"], "parameters": [dict(base, **bad)]}).run()
    session.expire_all()
    assert len(session.get(Character, committed["id"]).parameters) == 2

    # parameters を渡さなければ期間ごとの行は触らない
    UpdateCharacter({"id": committed["id"], "name": "別名"}).run()
    session.expire_all()
    assert len(session.get(Character, committed["id"]).parameters) == 2


def test_update_accepts_stamp_string_with_five_digit_year(session, world):
    committed = CommitCharacter(_draft(place_id=world["root"], start="2100")).run()

    updated = UpdateCharacter({"id": committed["id"], "start": "11556/01/01 00:00:00"}).run()
    assert updated["start"] == "11556/01/01 00:00:00"
    session.expire_all()
    assert session.get(Character, committed["id"]).start == Stamp(11556)

    story_id = session.query(Story).filter_by(place_id=world["root"]).one().id
    updated = UpdateStory({"id": story_id, "start": "11572"}).run()
    assert updated["start"] == "11572/01/01 00:00:00"
    session.expire_all()
    assert session.get(Story, story_id).start == Stamp(11572)


def test_commit_character_with_histories(session, world):
    histories = [
        {"start": None, "end": "2150", "description": "村の鍛冶屋の徒弟として働いていた"},
        {"start": "2150", "end": None, "description": "師の死後、鍛冶屋を継いで営んでいる"},
    ]
    result = CommitCharacter(_draft(place_id=world["root"], start="2100", histories=histories)).run()

    assert [row["description"] for row in result["histories"]] == [
        "師の死後、鍛冶屋を継いで営んでいる", "村の鍛冶屋の徒弟として働いていた"]
    record = session.get(Character, result["id"])
    assert session.query(CharacterHistory).filter_by(character_id=record.id).count() == 2


def test_update_character_histories(session, world):
    committed = CommitCharacter(_draft(place_id=world["root"], start="2100")).run()
    assert committed["histories"] == []

    histories = [{"start": None, "end": None, "description": "見習い"}]
    updated = UpdateCharacter({"id": committed["id"], "histories": histories}).run()
    assert [row["description"] for row in updated["histories"]] == ["見習い"]
    session.expire_all()
    [row] = session.get(Character, committed["id"]).histories
    row_id = row.id

    # 同じ位置の行は使い回し、配列をまるごと置き換える
    replaced = [dict(histories[0], description="親方"), {"start": "2150", "end": None, "description": "独立"}]
    updated = UpdateCharacter({"id": committed["id"], "histories": replaced}).run()
    assert {row["description"] for row in updated["histories"]} == {"親方", "独立"}
    session.expire_all()
    record = session.get(Character, committed["id"])
    assert len(record.histories) == 2
    assert any(row.id == row_id for row in record.histories)

    # histories を渡さなければ触らない
    UpdateCharacter({"id": committed["id"], "name": "別名"}).run()
    session.expire_all()
    assert len(session.get(Character, committed["id"]).histories) == 2


def test_update_requires_id():
    with pytest.raises(ValueError, match="id は必須"):
        UpdateCharacter({"name": "x"}).run()


def test_read_character_returns_levels(world):
    committed = CommitCharacter(
        _draft({"sincerity": "無", "imagination": "必"}, place_id=world["root"], start="2100")).run()
    sheet = ReadCharacter(committed["id"]).run()
    assert sheet["sincerity"] == "無" and sheet["imagination"] == "必"
    assert sheet["place"]["place_id"] == world["root"]


def test_read_character_returns_values_of_the_time(world):
    parameters = [build_parameter(sincerity="無", height=140.0),
                  build_parameter(start="2120", sincerity="高", height=None)]
    committed = CommitCharacter(
        _draft(place_id=world["root"], start="2100", parameters=parameters)).run()

    young = ReadCharacter(committed["id"], time="2110").run()
    grown = ReadCharacter(committed["id"], time="2130").run()
    assert (young["sincerity"], young["height"]) == ("無", 140.0)
    assert (grown["sincerity"], grown["height"]) == ("高", 140.0)
    assert len(grown["parameters"]) == 2
    # 時刻を渡さなければ、一番限る端が少ない行を採る。誕生(start=2100)を持つだけの最初の行と
    # 期間の始まる二番目の行(start=2120)が限る端の数(1つ)で並ぶので、後の行が勝つ
    assert ReadCharacter(committed["id"]).run()["sincerity"] == "高"


def test_commit_place_from_json_string_checks_parent_span(session, world):
    inside = {"name": "集落", "kind": "集落", "text": "", "parent_id": world["village"],
              "start": "2120", "end": "2180"}
    result = CommitPlace(json.dumps(inside, ensure_ascii=False)).run()
    assert session.get(Location, result["id"]).start == Stamp(2120)

    outside = dict(inside, name="はみ出す集落", end="2250")
    with pytest.raises(ValueError, match="end=2200/01/01 00:00:00 を超える"):
        CommitPlace(json.dumps(outside, ensure_ascii=False)).run()
