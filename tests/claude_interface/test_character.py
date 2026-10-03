"""claude が CLI から `show()` で呼ぶ、人物(`data_access_logic/character/`)の入口。"""
import random

import pytest

from data_access_logic import constants
from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.commit_character_location import CommitCharacterLocation
from data_access_logic.character.commit_character_relation import CommitCharacterRelation
from data_access_logic.character.create_random_character import CreateRandomCharacter
from data_access_logic.character.form import (
    CharacterCreateForm, CharacterForm, CharacterParameterForm, CharacterLocationCreateForm, CharacterLocationUpdateForm,
    CharacterRelationCreateForm, CharacterRelationUpdateForm, CharacterUpdateForm,
)
from data_access_logic.character.generate_character import GenerateCharacter
from data_access_logic.character.generate_characters import GenerateCharacters, resident_rooms
from data_access_logic.character.generator_models import CharacterNameMaterialSerialized, PersonNameDraft
from data_access_logic.character.naming import PersonNameCandidates, named
from data_access_logic.character.list_character_relations import ListCharacterRelations
from data_access_logic.character.list_characters import ListCharacters
from data_access_logic.character.read_character import ReadCharacter
from data_access_logic.character.read_surroundings import ReadSurroundings
from data_access_logic.character.record import (
    CharacterHistoryRow, CharacterLocationRow, CharacterParameterRow, CharacterRelationHistoryRow,
)
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.update_character_location import UpdateCharacterLocation
from data_access_logic.character.update_character_relation import UpdateCharacterRelation
from db.schema import PersonalityLevel, Stamp, get_env_session

_LEVELS = {
    "sincerity": PersonalityLevel.HIGH, "curiosity": PersonalityLevel.LOW, "proactivity": PersonalityLevel.MUST,
    "cooperativeness": PersonalityLevel.NONE, "sociability": PersonalityLevel.NORMAL,
    "emotional_expression": PersonalityLevel.HIGH, "self_esteem": PersonalityLevel.LOW,
    "self_efficacy": PersonalityLevel.NORMAL, "stress_resilience": PersonalityLevel.HIGH,
    "flexibility_of_values": PersonalityLevel.LOW, "sensitivity": PersonalityLevel.MUST,
    "imagination": PersonalityLevel.NORMAL,
}


def _parameter_row(start: str) -> CharacterParameterRow:
    return CharacterParameterRow(
        start=start, family_name="北原", sex="女", height=158.0, build="小柄", first_person="あたし",
        second_person="あんた", third_person="あいつ", tone="砕けた", dialect="西の訛り", **_LEVELS)


def test_commit_character(shown, world):
    result = shown(CommitCharacter(CharacterCreateForm(
        name="北原ミツ", text="市の香辛料売り", kind="人物", main_character=True,
        event_seeded=True, meme_seeded=True, location_id=world.location_id, start="1180/05/06", end="1250/01/01",
        parameters=[_parameter_row("1180/05/06")],
        histories=[CharacterHistoryRow(start=1195, description="市で店を開く")])))

    assert result["name"] == "北原ミツ"
    assert result["text"] == "市の香辛料売り"
    assert result["main_character"] is True
    assert result["start"] == "1180/05/06 00:00:00"
    assert result["end"] == "1250/01/01 00:00:00"
    assert result["parameters"][0]["family_name"] == "北原"
    assert result["parameters"][0]["imagination"] == "並"
    assert result["locations"] == [{"location_id": world.location_id, "start": "1180/05/06 00:00:00",
                                 "end": "1250/01/01 00:00:00"}]
    assert result["histories"][0]["description"] == "市で店を開く"


def test_commit_character_location(shown, world):
    result = shown(CommitCharacterLocation(CharacterLocationCreateForm(
        character_id=world.character_ids[0], location_id=world.neighbor_id, start="1201/01/01", end="1202/01/01")))

    assert result["character_id"] == world.character_ids[0]
    assert result["location_id"] == world.neighbor_id
    assert (result["start"], result["end"]) == ("1201/01/01 00:00:00", "1202/01/01 00:00:00")


def test_commit_character_relation(shown, world):
    result = shown(CommitCharacterRelation(CharacterRelationCreateForm(
        character_1_id=world.character_ids[1], character_2_id=world.character_ids[0], relation="商売敵",
        text="市で客を取り合う", start="1200/04/01", end="1210/01/01",
        histories=[CharacterRelationHistoryRow(start=1205, description="値下げで競り合う")])))

    assert (result["character_1_id"], result["character_2_id"]) == (world.character_ids[1], world.character_ids[0])
    assert result["relation"] == "商売敵"
    assert result["text"] == "市で客を取り合う"
    assert (result["start"], result["end"]) == ("1200/04/01 00:00:00", "1210/01/01 00:00:00")
    assert result["histories"] == [{"start": 1205, "description": "値下げで競り合う"}]


def test_create_random_character(shown):
    result = shown(CreateRandomCharacter(name="乱数の人", text="乱数で作った人", main_character=True))

    assert result["name"] == "乱数の人"
    assert result["text"] == "乱数で作った人"
    assert result["main_character"] is True
    # 返した形のまま確定する入口の引数に渡せる
    CharacterCreateForm.model_validate(result)


def test_generate_character(shown, world, mock_ai):
    result = shown(GenerateCharacter(
        character=CharacterForm(
            name="生成の人", text="市に流れ着いた楽師", kind="人物", main_character=True, start="1180/01/01",
            end="1260/01/01", location_id=world.location_id,
            parameters=[CharacterParameterForm(
                family_name="南条", sex="男", build="大柄", first_person="俺", second_person="お前",
                third_person="奴", tone="荒い", dialect="港言葉", **_LEVELS)]),
        time="1200/04/01", seed=1))

    assert result["main_character"] is True
    assert result["locations"][0]["location_id"] == world.location_id
    parameter = result["parameters"][0]
    assert (parameter["sex"], parameter["build"], parameter["tone"]) == ("男", "大柄", "荒い")
    assert parameter["sincerity"] == "高"
    assert mock_ai.calls


def test_generate_characters(shown, world, mock_ai):
    result = shown(GenerateCharacters(
        location_ids=[world.location_id], time="1200/04/01", count=(2, 2), person=True, seed=2))

    assert len(result) == 2
    assert {row["location_id"] for row in result} == {world.location_id}
    assert mock_ai.calls


def test_generate_characters_stops_at_resident_limit(shown, world, mock_ai, monkeypatch: pytest.MonkeyPatch):
    with get_env_session() as s:
        monkeypatch.setattr(constants, "RESIDENT_LIMITS", {"都市": 1000})
        residents = 1000 - resident_rooms(s, [world.location_id], Stamp.parse("1200/04/01"))[world.location_id]
    monkeypatch.setattr(constants, "RESIDENT_LIMITS", {"都市": residents + 1})

    result = shown(GenerateCharacters(
        location_ids=[world.location_id], time="1200/04/01", count=(3, 3), person=True, seed=2))

    assert len(result) == 1


class _NamingAI:
    def __init__(self, names: list[str]):
        self.names = names

    def generate(self, prompt, output, system=None, timeout=None, model=None, effort=None):
        return PersonNameCandidates(candidates=[PersonNameDraft(name=name, family_name="") for name in self.names])


def test_named_avoids_names_in_the_same_place():
    material = CharacterNameMaterialSerialized(kind="人物", text="市の荷運び", age=30, avoided_names=["ジャコモ", "グイド"])
    ai = _NamingAI(["ジャコモ", "グイド", "ルカ", "ルカ", "エリオ"])

    drafts = [named(ai, random.Random(seed), material, True) for seed in range(20)]

    assert {draft.name for draft in drafts if draft is not None} == {"ルカ", "エリオ"}


def test_named_keeps_the_authors_name():
    material = CharacterNameMaterialSerialized(kind="人物", text="市の荷運び", age=30, avoided_names=["ジャコモ"],
                                               hint_name="ジャコモ")

    draft = named(_NamingAI(["ジャコモ", "ルカ"]), random.Random(0), material, True)

    assert draft is not None and draft.name == "ジャコモ"


def test_list_character_relations(shown, world):
    result = shown(ListCharacterRelations(character_id=world.character_ids[0]))

    assert world.relation_id in [row["id"] for row in result]


def test_list_characters(shown, world):
    result = shown(ListCharacters())

    assert set(world.character_ids) <= {row["id"] for row in result}


def test_read_character(shown, world):
    result = shown(ReadCharacter(character_id=world.character_ids[0], time="1200/04/02", count=3))

    assert result["id"] == world.character_ids[0]
    assert result["name"] == "テスト太郎"
    assert result["text"] == "テスト太郎の説明"
    # その時刻までに起きた行だけを、始まりの古い順に出す(年未定の行は出さない)
    assert [history["description"] for history in result["histories"]] == ["テスト太郎の来歴"]


def test_read_character_without_time(shown, world):
    result = shown(ReadCharacter(character_id=world.character_ids[0]))

    # 時刻を渡さなければ、年未定の行も最後に出す
    assert [history["description"] for history in result["histories"]] == ["テスト太郎の来歴", "テスト太郎の年未定の構想"]


def test_read_surroundings(shown, world):
    result = shown(ReadSurroundings(character_id=world.character_ids[0], time="1200/04/02", reach=30))

    assert result["character_id"] == world.character_ids[0]
    assert result["reach"] == 30
    assert world.character_ids[1] in [character["id"] for character in result["characters"]]
    assert world.event_id in [event["id"] for event in result["events"]]


def test_update_character(shown, world):
    result = shown(UpdateCharacter(CharacterUpdateForm(
        id=world.character_ids[1], name="テスト花代", text="改名した", kind="人物",
        main_character=True, event_seeded=False, meme_seeded=False, start="1171/02/03", end="1261/04/05",
        parameters=[_parameter_row("1171/02/03")],
        locations=[CharacterLocationRow(location_id=world.neighbor_id, start="1171/02/03", end="1261/04/05")],
        histories=[CharacterHistoryRow(start=1200, description="改名して村へ移った")])))

    assert result["name"] == "テスト花代"
    assert result["text"] == "改名した"
    assert result["main_character"] is True
    assert (result["event_seeded"], result["meme_seeded"]) == (False, False)
    assert (result["start"], result["end"]) == ("1171/02/03 00:00:00", "1261/04/05 00:00:00")
    assert result["parameters"][0]["dialect"] == "西の訛り"
    assert [location["location_id"] for location in result["locations"]] == [world.neighbor_id]
    assert [history["description"] for history in result["histories"]] == ["改名して村へ移った"]


def test_update_character_location(shown, world):
    result = shown(UpdateCharacterLocation(CharacterLocationUpdateForm(
        id=world.character_location_id, character_id=world.character_ids[0], location_id=world.neighbor_id,
        start="1190/01/01", end="1199/12/31")))

    assert result["id"] == world.character_location_id
    assert result["location_id"] == world.neighbor_id
    assert (result["start"], result["end"]) == ("1190/01/01 00:00:00", "1199/12/31 00:00:00")


def test_update_character_relation(shown, world):
    result = shown(UpdateCharacterRelation(CharacterRelationUpdateForm(
        id=world.relation_id, character_1_id=world.character_ids[1], character_2_id=world.character_ids[0],
        relation="許嫁", text="親が決めた", start="1190/01/01", end="1205/01/01",
        histories=[CharacterRelationHistoryRow(start=1195, description="縁談が流れかける")])))

    assert (result["character_1_id"], result["character_2_id"]) == (world.character_ids[1], world.character_ids[0])
    assert (result["relation"], result["text"]) == ("許嫁", "親が決めた")
    assert (result["start"], result["end"]) == ("1190/01/01 00:00:00", "1205/01/01 00:00:00")
    assert result["histories"] == [{"start": 1195, "description": "縁談が流れかける"}]

    # 来歴を渡さなければ、今の行はそのまま
    result = shown(UpdateCharacterRelation(CharacterRelationUpdateForm(id=world.relation_id, text="親が決めた縁")))
    assert result["histories"] == [{"start": 1195, "description": "縁談が流れかける"}]
