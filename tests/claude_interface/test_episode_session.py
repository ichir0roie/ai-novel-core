"""来歴の公開度と知る人、人物が知ることのできるデータ(`character/read_knowledge`)、話のセッション(`episode_session/`)。"""
import pytest

from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.form import CharacterCreateForm, CharacterUpdateForm
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.delete_character import DeleteCharacter
from data_access_logic.episode.delete_episode import DeleteEpisode
from data_access_logic.episode_session.add_turns import AddTurns
from data_access_logic.episode_session.answer_turn import AnswerTurn
from data_access_logic.episode_session.close_session import CloseSession
from data_access_logic.episode_session.form import TurnAnswer, TurnRequest
from data_access_logic.episode_session.read_session import ReadSession
from data_access_logic.episode_session.read_turn import ReadTurn
from data_access_logic.idea.form import IdeaUpdateForm
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.update_idea import UpdateIdea
from db.schema import Visibility
from tool import episode_session


def test_new_character_is_public_and_its_history_is_private(shown):
    result = shown(CommitCharacter(CharacterCreateForm(
        name="知る人テスト", text="説明", histories=[CharacterHistoryRow(start=1195, description="市で店を開く")])))

    assert (result["visibility"], result["knower_ids"]) == ("public", [result["id"]])
    assert result["histories"] == [{"start": 1195, "visibility": "private", "description": "市で店を開く",
                                    "knower_ids": [result["id"]]}]


def test_knower_must_exist(world):
    with pytest.raises(ValueError, match="knower_ids"):
        UpdateCharacter(CharacterUpdateForm(id=world.character_ids[0], knower_ids=[10**9])).run()


def test_delete_character_removes_its_knower_rows(shown, world):
    taro, _ = world.character_ids
    other = shown(CommitCharacter(CharacterCreateForm(name="消える人", text="説明")))
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, visibility=Visibility.PRIVATE, knower_ids=[taro, other["id"]])))
    shown(DeleteCharacter(character_id=other["id"]))

    assert shown(ReadKnowledge(character_id=taro, time="1200/01/01"))["自分"]["人物像"] == "テスト太郎の説明"


def test_update_history_knowers(shown, world):
    taro, hanako = world.character_ids
    replaced = shown(UpdateCharacter(CharacterUpdateForm(id=hanako, histories=[
        CharacterHistoryRow(start=1191, description="秘密", knower_ids=[hanako, taro])])))
    kept = shown(UpdateCharacter(CharacterUpdateForm(id=hanako, histories=[
        CharacterHistoryRow(start=1191, description="秘密(書き直し)")])))

    assert replaced["histories"][0]["knower_ids"] == [hanako, taro]
    assert kept["histories"][0]["knower_ids"] == [hanako, taro]


def test_read_knowledge(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, text="太郎の芯\n\n# plot\n\n先の筋書き\n", histories=[
        CharacterHistoryRow(start=1190, description="太郎の秘密", knower_ids=[taro])])))
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, text="花子の芯\n\n# plot\n\n花子の先", histories=[
        CharacterHistoryRow(start=1190, visibility=Visibility.PUBLIC, description="公の事"),
        CharacterHistoryRow(start=1191, description="花子だけの秘密", knower_ids=[hanako]),
        CharacterHistoryRow(start=1192, description="太郎も知る秘密", knower_ids=[hanako, taro]),
        CharacterHistoryRow(start=1250, visibility=Visibility.PUBLIC, description="先のこと")])))
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, histories=[
        IdeaHistoryRow(start=1150, visibility=Visibility.PUBLIC, description="都に広まる"),
        IdeaHistoryRow(start=1160, description="炉の作り方は秘匿される", knower_ids=[taro]),
        IdeaHistoryRow(start=1170, description="誰も知らない欠陥")])))

    result = shown(ReadKnowledge(character_id=taro, time="1200/01/01"))

    me = result["自分"]
    assert me["人物像"] == "太郎の芯"
    assert [history["来歴"] for history in me["来歴(古い順)"]] == ["太郎の秘密"]
    hanako_known = next(character for character in result["知っている人物"] if character["名前"] == "テスト花子")
    assert hanako_known["人物像"] == "花子の芯"
    assert [history["来歴"] for history in hanako_known["来歴(古い順)"]] == ["公の事", "太郎も知る秘密"]
    idea = next(idea for idea in result["知っているアイデア"] if idea["名前"] == "テスト魔導")
    assert (idea["呼び名"], idea["説明"]) == ("テスト術", "テスト用の技術")
    assert [history["来歴"] for history in idea["来歴(古い順)"]] == ["都に広まる", "炉の作り方は秘匿される"]


def test_read_knowledge_hides_private_texts(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, visibility=Visibility.PRIVATE, knower_ids=[])))
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, visibility=Visibility.PRIVATE)))
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, visibility=Visibility.PRIVATE, knower_ids=[hanako])))

    result = shown(ReadKnowledge(character_id=taro, time="1200/01/01"))
    hanako_view = shown(ReadKnowledge(character_id=hanako, time="1200/01/01"))

    # 本人も知る人から外せば、自分の本文を知らない。関係のある人物の名前は分かるが、非公開の本文は分からない
    assert result["自分"]["人物像"] is None
    assert [(character["名前"], character["人物像"]) for character in result["知っている人物"]] == [("テスト花子", None)]
    assert "テスト魔導" not in [idea["名前"] for idea in result["知っているアイデア"]]
    assert hanako_view["自分"]["人物像"] == "テスト花子の説明"
    assert "テスト魔導" in [idea["名前"] for idea in hanako_view["知っているアイデア"]]


def test_read_knowledge_skips_unrelated_cast(shown, world):
    stranger = shown(CommitCharacter(CharacterCreateForm(name="初対面の人", text="説明")))
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=stranger["id"], request="市に着いた")]))

    result = shown(ReadKnowledge(character_id=world.character_ids[0], time="1200/01/01"))

    assert "初対面の人" not in [character["名前"] for character in result["知っている人物"]]


def test_session_turns(shown, world):
    taro, hanako = world.character_ids
    added = shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, time="1200/04/01 12:00:00", request="市で花子を見かけた"),
        TurnRequest(character_id=hanako, request="太郎が手を振った")]))
    taro_turn, hanako_turn = (record["id"] for record in added)

    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "waiting"
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=taro))["record"]["id"] == taro_turn
    with pytest.raises(ValueError, match="まだ番が来ていない"):
        AnswerTurn(record_id=hanako_turn, answer=TurnAnswer(action="手を振り返す")).run()

    shown(AnswerTurn(record_id=taro_turn, answer=TurnAnswer(thought="久しぶりだ", action="手を振る", speech="よう")))
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "turn"
    shown(AnswerTurn(record_id=hanako_turn, answer=TurnAnswer(action="手を振り返す")))
    shown(CloseSession(episode_id=world.episode_id))

    assert shown(ReadTurn(episode_id=world.episode_id, character_id=taro))["status"] == "closed"
    records = shown(ReadSession(episode_id=world.episode_id))
    assert [(record["character"]["name"], record["closing"]) for record in records] == [
        ("テスト太郎", False), ("テスト花子", False), ("テスト太郎", True), ("テスト花子", True)]
    assert (records[0]["speech"], records[0]["time"]) == ("よう", "1200/04/01 12:00:00")

    shown(DeleteEpisode(episode_id=world.episode_id))
    assert shown(ReadSession(episode_id=world.episode_id)) == []


def test_wait_turn_returns_when_the_turn_comes(shown, world, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=taro, request="市に着いた")]))

    assert episode_session.wait_turn(world.episode_id, hanako, interval=0.01, timeout=0.02) == {"status": "timeout"}
    assert episode_session.wait_turn(world.episode_id, taro, interval=0.01, timeout=0.02)["status"] == "turn"
