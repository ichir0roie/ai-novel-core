"""人物のスキル(`character_skill`)と、その来歴(`character_skill_history`)を知る相手。"""
import pytest
from sqlalchemy import select

from data_access_logic.character.commit_character_skill import CommitCharacterSkill
from data_access_logic.character.delete_character import DeleteCharacter
from data_access_logic.character.delete_character_skill import DeleteCharacterSkill
from data_access_logic.character.form import (
    CharacterCreateForm, CharacterSkillCreateForm, CharacterSkillUpdateForm, KnowledgeChange, KnowledgeForm,
)
from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.read_knowable_rows import ReadKnowableRows
from data_access_logic.character.read_known_rows import ReadKnownRows
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.record import CharacterSkillHistoryRow
from data_access_logic.character.update_character_skill import UpdateCharacterSkill
from data_access_logic.character.update_knowledge import UpdateKnowledge
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.episode.read_episode_brief import ReadEpisodeBrief
from data_access_logic.knowers import KnowerRow
from data_access_logic.location.delete_location import DeleteLocation
from data_access_logic.location.commit_location import CommitLocation
from data_access_logic.location.form import LocationCreateForm
from db.schema import CharacterSkill, CharacterSkillHistory, CharacterSkillHistoryKnower, get_env_session


def _skill(person: dict, name: str) -> dict | None:
    return next((skill for skill in person["スキル"] if skill["名前"] == name), None)


def test_commit_character_skill_knows_its_owner(shown, world):
    taro, hanako = world.character_ids

    skill = shown(CommitCharacterSkill(CharacterSkillCreateForm(
        character_id=taro, name="テスト剣術", text="型を重んじる剣", histories=[
            CharacterSkillHistoryRow(start=1185, description="道場に入る"),
            CharacterSkillHistoryRow(start=1195, description="免許皆伝", knowers=[KnowerRow(knower_id=hanako)])])))

    assert (skill["character_id"], skill["name"], skill["text"]) == (taro, "テスト剣術", "型を重んじる剣")
    # knowers を渡さない新しい行は、スキルを持つ本人だけが知る
    by_description = {history["description"]: history["knowers"] for history in skill["histories"]}
    assert by_description == {"道場に入る": [{"knower_id": taro, "location_id": None, "start": None}],
                              "免許皆伝": [{"knower_id": hanako, "location_id": None, "start": None}]}


def test_commit_character_skill_needs_the_character(shown):
    with pytest.raises(UnknownRecordError):
        CommitCharacterSkill(CharacterSkillCreateForm(character_id=0, name="無い人の技")).result()


def test_update_character_skill_keeps_knowers_of_kept_rows(shown, world):
    taro, hanako = world.character_ids
    skill = shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=taro, name="テスト弓術", histories=[
        CharacterSkillHistoryRow(start=1185, description="弓を習う", knowers=[KnowerRow(knower_id=hanako)])])))

    updated = shown(UpdateCharacterSkill(CharacterSkillUpdateForm(id=skill["id"], name="テスト弓術改", histories=[
        CharacterSkillHistoryRow(start=1185, description="弓を習う"),
        CharacterSkillHistoryRow(start=1198, description="遠矢を覚える")])))

    assert updated["name"] == "テスト弓術改"
    # knowers を渡さない行は、今ある行なら知る相手をそのままにし、新しい行なら本人だけにする
    assert {history["description"]: history["knowers"] for history in updated["histories"]} == {
        "弓を習う": [{"knower_id": hanako, "location_id": None, "start": None}],
        "遠矢を覚える": [{"knower_id": taro, "location_id": None, "start": None}]}


def test_read_knowledge_skills_only_known_rows_until_the_time(shown, world):
    taro, hanako = world.character_ids
    shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=taro, name="テスト火術", text="作者だけの仕組み", histories=[
        CharacterSkillHistoryRow(start=1190, description="火を起こせるようになる"),
        CharacterSkillHistoryRow(start=1195, description="人に隠した奥義", knowers=[]),
        CharacterSkillHistoryRow(start=1250, description="先に覚えること"),
        CharacterSkillHistoryRow(description="年未定の構想")])))
    shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=hanako, name="テスト治癒", histories=[
        CharacterSkillHistoryRow(start=1190, description="傷をふさぐ", knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro)]),
        CharacterSkillHistoryRow(start=1192, description="花子だけの秘術")])))
    shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=hanako, name="テスト隠形", histories=[
        CharacterSkillHistoryRow(start=1190, description="気配を消す")])))
    shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=taro, name="テスト未来の技", histories=[
        CharacterSkillHistoryRow(start=1250, description="後で覚える")])))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    # 話の時刻(1200 年)までに起きた、知っている行だけ。本質(text)は渡さない
    assert _skill(result["自分"], "テスト火術") == {"名前": "テスト火術", "来歴(古い順)": [{"いつ": "10年前", "来歴": "火を起こせるようになる"}]}
    assert "作者だけの仕組み" not in str(result)
    # 知っている行が一つも無いスキルは、持っていることも知らない
    assert _skill(result["自分"], "テスト未来の技") is None
    hanako_known = next(character for character in result["知っている人物"] if character["名前"] == "テスト花子")
    assert _skill(hanako_known, "テスト治癒") == {"名前": "テスト治癒", "来歴(古い順)": [{"いつ": "10年前", "来歴": "傷をふさぐ"}]}
    assert _skill(hanako_known, "テスト隠形") is None


def test_episode_brief_has_skills_with_knowers(shown, world):
    taro, hanako = world.character_ids
    shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=hanako, name="テスト治癒", text="傷の治りを早める", histories=[
        CharacterSkillHistoryRow(start=1190, description="傷をふさぐ", knowers=[KnowerRow(knower_id=taro, start="1199/01/01")]),
        CharacterSkillHistoryRow(start=1250, description="先に覚えること")])))
    shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=hanako, name="テスト未来の技", histories=[
        CharacterSkillHistoryRow(start=1250, description="後で覚える")])))

    result = shown(ReadEpisodeBrief(episode_id=world.episode_id))

    hanako_row = next(member for member in result["この話"]["登場人物"] if member["人物id"] == hanako)
    # 作者には、知る相手に関わらず話の時刻までに始まった行を、本質と知る相手を添えて渡す。まだ持っていないスキルは渡さない
    assert hanako_row["スキル"] == [{"名前": "テスト治癒", "本質": "傷の治りを早める", "来歴(古い順)": [
        {"年": 1190, "来歴": "傷をふさぐ", "知る相手": [{"人物": "テスト太郎", "場所": None, "知った時刻": "1199/01/01 00:00:00"}]}]}]


def test_update_knowledge_of_skill_histories(shown, world):
    taro, hanako = world.character_ids
    skill = shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=hanako, name="テスト隠形", histories=[
        CharacterSkillHistoryRow(start=1185, description="気配を消す"),
        CharacterSkillHistoryRow(start=1188, description="太郎が忘れる技", knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro)])])))

    [entry] = [entry for entry in shown(ReadKnowableRows(character_id=hanako))["character_skills"] if entry["id"] == skill["id"]]
    assert entry["name"] == "テスト隠形" and "text" not in entry
    told, forgotten = (row["id"] for row in entry["histories"])

    result = shown(UpdateKnowledge(KnowledgeForm(knower_id=taro, character_skill_histories=[
        KnowledgeChange(id=told, known=True, start="1195/01/01"), KnowledgeChange(id=forgotten, known=False)])))

    assert {"id": told, "character_id": hanako} in result["character_skill_histories"]
    assert forgotten not in [row["id"] for row in result["character_skill_histories"]]
    assert result == shown(ReadKnownRows(knower_id=taro))
    knowledge = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))
    hanako_known = next(character for character in knowledge["知っている人物"] if character["名前"] == "テスト花子")
    assert _skill(hanako_known, "テスト隠形") == {"名前": "テスト隠形", "来歴(古い順)": [{"いつ": "15年前", "来歴": "気配を消す"}]}


def test_delete_character_skill(shown, world):
    taro, hanako = world.character_ids
    skill = shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=taro, name="テスト消す技", histories=[
        CharacterSkillHistoryRow(start=1190, description="覚える", knowers=[KnowerRow(knower_id=hanako)])])))

    assert shown(DeleteCharacterSkill(skill["id"])) == {"id": skill["id"], "character_id": taro, "name": "テスト消す技"}

    with get_env_session() as s:
        assert s.get(CharacterSkill, skill["id"]) is None
        assert s.scalars(select(CharacterSkillHistory).where(CharacterSkillHistory.character_skill_id == skill["id"])).all() == []


def test_delete_character_removes_its_skills_and_knowers(shown, world):
    taro, _ = world.character_ids
    doomed = shown(CommitCharacter(CharacterCreateForm(name="消える人")))
    own = shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=doomed["id"], name="消える人の技", histories=[
        CharacterSkillHistoryRow(start=1190, description="覚える")])))
    other = shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=taro, name="テスト見られた技", histories=[
        CharacterSkillHistoryRow(start=1190, description="見られる", knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=doomed["id"])])])))

    shown(DeleteCharacter(doomed["id"]))

    with get_env_session() as s:
        assert s.get(CharacterSkill, own["id"]) is None
        knowers = s.scalars(select(CharacterSkillHistoryKnower).join(CharacterSkillHistory)
                            .where(CharacterSkillHistory.character_skill_id == other["id"])).all()
        assert [knower.knower_id for knower in knowers] == [taro]


def test_delete_location_removes_skill_history_knowers(shown, world):
    taro, _ = world.character_ids
    place = shown(CommitLocation(LocationCreateForm(name="消える里", kind="村", parent_id=world.planet_id)))
    skill = shown(CommitCharacterSkill(CharacterSkillCreateForm(character_id=taro, name="テスト里の技", histories=[
        CharacterSkillHistoryRow(start=1190, description="里に伝わる", knowers=[KnowerRow(location_id=place["id"])])])))

    shown(DeleteLocation(place["id"]))

    with get_env_session() as s:
        [history] = s.scalars(select(CharacterSkillHistory).where(CharacterSkillHistory.character_skill_id == skill["id"])).all()
        assert history.knowers == []
