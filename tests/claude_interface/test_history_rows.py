"""来歴・呼び名の行を id で指して一つだけ直す入口と、配列で渡すときに id で今ある行に当てること。"""
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from data_access_logic.character.add_knower import AddKnower
from data_access_logic.character.append_relation_history import AppendRelationHistory
from data_access_logic.character.commit_character_skill import CommitCharacterSkill
from data_access_logic.character.form import (
    CharacterHistoryChange, CharacterRelationHistoryChange, CharacterSkillCreateForm, CharacterSkillHistoryChange,
    CharacterUpdateForm,
)
from data_access_logic.character.read_character import ReadCharacter
from data_access_logic.character.record import CharacterHistoryRow, CharacterRelationHistoryRow, CharacterSkillHistoryRow
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.update_history import UpdateCharacterHistory
from data_access_logic.character.update_relation_history import UpdateRelationHistory
from data_access_logic.character.update_skill_history import UpdateSkillHistory
from data_access_logic.idea.form import IdeaHistoryChange
from data_access_logic.idea.update_history import UpdateIdeaHistory
from data_access_logic.knowers import KnowerRow
from data_access_logic.location.append_history import AppendLocationHistory
from data_access_logic.location.form import LocationHistoryChange
from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.location.update_history import UpdateLocationHistory
from db.guard import ProtectedRowError
from db.schema import Character, CharacterHistory, IdeaHistory, get_env_session
from db.writer import writing


def _histories(shown, character_id: int) -> list[dict]:
    return shown(ReadCharacter(character_id=character_id))["histories"]


def test_update_character_history_changes_only_the_given_fields_of_one_row(shown, world):
    character_id = world.character_ids[0]
    dated, undated = _histories(shown, character_id)

    changed = shown(UpdateCharacterHistory(history_id=dated["id"], history=CharacterHistoryChange(
        description="直した来歴", kind="記憶")))

    assert changed == {**dated, "description": "直した来歴", "kind": "記憶"}
    assert _histories(shown, character_id) == [changed, undated]


def test_update_character_history_clears_a_field_given_as_null_and_replaces_knowers(shown, world):
    character_id, other_id = world.character_ids
    dated = _histories(shown, character_id)[0]

    changed = shown(UpdateCharacterHistory(history_id=dated["id"], history=CharacterHistoryChange.model_validate(
        {"start": None, "knowers": [{"knower_id": other_id}]})))

    assert changed["start"] is None and changed["description"] == dated["description"]
    assert [knower["knower_id"] for knower in changed["knowers"]] == [other_id]


def test_history_changes_cannot_empty_required_fields():
    with pytest.raises(ValidationError):
        CharacterHistoryChange.model_validate({"description": None})
    with pytest.raises(ValidationError):
        IdeaHistoryChange.model_validate({"name": ""})


def test_update_entrances_for_skill_relation_location_and_idea_histories(shown, world):
    character_id = world.character_ids[0]
    skill = shown(CommitCharacterSkill(CharacterSkillCreateForm(
        character_id=character_id, name="テスト剣術",
        histories=[CharacterSkillHistoryRow(start="1190", description="剣を習う"),
                   CharacterSkillHistoryRow(start="1195", description="師範になる")])))
    relation_row = shown(AppendRelationHistory(character_relation_id=world.relation_id, history=CharacterRelationHistoryRow(
        start="1200", description="港で会う")))
    place_row = shown(AppendLocationHistory(location_id=world.location_id, history=LocationHistoryRow(
        start="1200", description="港で火事が起きる")))
    with get_env_session() as s:
        idea_row_id = s.scalars(select(IdeaHistory.id).where(IdeaHistory.idea_id == world.idea_id)).one()

    learned = next(row for row in skill["histories"] if row["description"] == "剣を習う")
    skill_row = shown(UpdateSkillHistory(history_id=learned["id"], history=CharacterSkillHistoryChange(end="1195")))
    relation = shown(UpdateRelationHistory(history_id=relation_row["id"], history=CharacterRelationHistoryChange(
        description="港で再会する")))
    place = shown(UpdateLocationHistory(history_id=place_row["id"], history=LocationHistoryChange(
        description="港で大火事が起きる")))
    called = shown(UpdateIdeaHistory(history_id=idea_row_id, history=IdeaHistoryChange(detail="都での古い呼び名")))

    assert (skill_row["description"], skill_row["end"]) == ("剣を習う", "1195/01/01 00:00:00")
    assert (relation["start"], relation["description"]) == ("1200/01/01 00:00:00", "港で再会する")
    assert place["description"] == "港で大火事が起きる"
    assert [knower["location_id"] for knower in place["knowers"]] == [world.location_id]
    assert (called["name"], called["detail"]) == ("テスト術", "都での古い呼び名")


def test_replacing_histories_matches_rows_by_id(shown, world):
    character_id, other_id = world.character_ids
    dated, undated = _histories(shown, character_id)
    shown(AddKnower(table="character_history", row_id=dated["id"], knower=KnowerRow(knower_id=other_id)))
    moved = CharacterHistoryRow(id=dated["id"], start="1191", description=dated["description"])

    shown(UpdateCharacter(CharacterUpdateForm(id=character_id, histories=[
        moved, CharacterHistoryRow.model_validate(undated), CharacterHistoryRow(start="1192", description="足した来歴")])))

    rows = _histories(shown, character_id)
    assert [row["id"] for row in rows[:1]] == [dated["id"]] and rows[0]["start"] == "1191/01/01 00:00:00"
    # 始まりを変えても同じ行なので、知る相手はそのまま残る
    assert [knower["knower_id"] for knower in rows[0]["knowers"]] == [other_id]
    assert [row["description"] for row in rows] == [dated["description"], "足した来歴", undated["description"]]
    with pytest.raises(ValueError, match="この行の子の行に無い"):
        UpdateCharacter(CharacterUpdateForm(id=character_id, histories=[
            CharacterHistoryRow(id=2_000_000_000, description="無い行")])).run()


def test_append_writer_cannot_rewrite_an_author_row(world):
    with get_env_session() as s:
        row_id = s.get_one(Character, world.character_ids[0]).histories[0].id
    with pytest.raises(ProtectedRowError), writing("ai_append"):
        UpdateCharacterHistory(history_id=row_id, history=CharacterHistoryChange(description="書き換え")).run()
    with get_env_session() as s:
        assert s.get_one(CharacterHistory, row_id).description != "書き換え"
