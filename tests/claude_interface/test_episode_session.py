"""本文・来歴を知る相手、人物が知ることのできるデータ(`character/read_knowledge`)と見た目(`read_appearance`)、
話のセッション(`episode_session/`)。"""
import pytest
from pydantic import ValidationError

from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.delete_character import DeleteCharacter
from data_access_logic.character.form import CharacterCreateForm, CharacterUpdateForm
from data_access_logic.character.read_appearance import ReadAppearance
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.episode.delete_episode import DeleteEpisode
from data_access_logic.episode_session.add_turns import AddTurns
from data_access_logic.episode_session.answer_turn import AnswerTurn
from data_access_logic.episode_session.close_session import CloseSession
from data_access_logic.episode_session.form import TurnAnswer, TurnRequest
from data_access_logic.episode_session.read_session import ReadSession
from data_access_logic.episode_session.read_turn import ReadTurn
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.update_idea import UpdateIdea
from data_access_logic.knowers import KnowerRow
from tool import episode_session


def _histories(person: dict) -> list[str]:
    return [history["来歴"] for history in person["来歴(古い順)"]]


def test_new_character_knows_itself_and_its_history(shown):
    result = shown(CommitCharacter(CharacterCreateForm(
        name="知る人テスト", text="説明", histories=[CharacterHistoryRow(start=1195, description="市で店を開く")])))

    oneself = [{"knower_id": result["id"], "location_id": None, "start": None}]
    assert result["knowers"] == oneself
    assert result["histories"][0]["knowers"] == oneself


def test_knower_is_a_character_or_a_location(world):
    with pytest.raises(ValidationError, match="どちらか一方"):
        KnowerRow()
    with pytest.raises(ValidationError, match="どちらか一方"):
        KnowerRow(knower_id=world.character_ids[0], location_id=world.location_id)
    with pytest.raises(ValueError, match="knowers.knower_id"):
        UpdateCharacter(CharacterUpdateForm(id=world.character_ids[0], knowers=[KnowerRow(knower_id=10**9)])).run()


def test_delete_character_removes_its_knower_rows(shown, world):
    taro, _ = world.character_ids
    other = shown(CommitCharacter(CharacterCreateForm(name="消える人", text="説明")))
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=other["id"])])))
    shown(DeleteCharacter(character_id=other["id"]))

    assert shown(ReadKnowledge(character_id=taro, time="1200/01/01"))["自分"]["人物像"] == "テスト太郎の説明"


def test_read_knowledge(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(
        id=taro, appearance="背が高い", text="太郎の芯", meme="- 今表: 太郎のミーム", principle="太郎の行動原理",
        plot="太郎の先の筋書き",
        histories=[CharacterHistoryRow(start=1190, description="太郎の秘密", knowers=[KnowerRow(knower_id=taro)])])))
    shown(UpdateCharacter(CharacterUpdateForm(
        id=hanako, appearance="髪が赤い", text="花子の芯", meme="- 裏: 花子のミーム", plot="花子の先",
        knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro, start="1195/01/01")],
        histories=[
            CharacterHistoryRow(start=1190, description="都の噂", knowers=[KnowerRow(location_id=world.location_id)]),
            CharacterHistoryRow(start=1191, description="花子だけの秘密", knowers=[KnowerRow(knower_id=hanako)]),
            CharacterHistoryRow(start=1192, description="太郎も知る秘密",
                                knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro, start="1199/01/01")]),
            CharacterHistoryRow(start=1193, description="後で知る秘密", knowers=[KnowerRow(knower_id=taro, start="1201/01/01")]),
            CharacterHistoryRow(start=1250, description="先のこと", knowers=[KnowerRow(location_id=world.location_id)])])))
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="テスト術", detail="都での呼び名"),
        IdeaHistoryRow(location_id=world.neighbor_id, name="村の隠し名", knowers=[KnowerRow(knower_id=taro)]),
        IdeaHistoryRow(location_id=world.neighbor_id, name="誰も知らない名")])))

    result = shown(ReadKnowledge(character_id=taro, time="1200/01/01"))

    me = result["自分"]
    assert (me["外見"], me["人物像"], me["ミーム"], me["行動原理"]) == ("背が高い", "太郎の芯", "- 今表: 太郎のミーム", "太郎の行動原理")
    assert "筋書き" not in me
    assert _histories(me) == ["太郎の秘密"]
    hanako_known = next(character for character in result["知っている人物"] if character["名前"] == "テスト花子")
    assert (hanako_known["外見"], hanako_known["人物像"]) == ("髪が赤い", "花子の芯")
    assert "ミーム" not in hanako_known
    assert _histories(hanako_known) == ["都の噂", "太郎も知る秘密"]
    idea = next(idea for idea in result["知っているアイデア"] if idea["名前"] == "テスト魔導")
    assert (idea["呼び名"], idea["説明"]) == ("テスト術", "テスト用の技術")
    assert [name["呼び名"] for name in idea["知っている呼び名"]] == ["テスト術", "村の隠し名"]


def test_read_knowledge_without_knowing(shown, world, mock_ai):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, meme="- 今表: 残るミーム", knowers=[])))
    shown(CommitIdea(IdeaCreateForm(name="村の秘薬", kind="技術", text="村だけの薬", location_id=world.neighbor_id,
                                    knowers=[KnowerRow(knower_id=taro)]), fact_check=False))
    shown(CommitIdea(IdeaCreateForm(name="遠い技", kind="技術", text="村だけの技", location_id=world.neighbor_id),
                     fact_check=False))

    result = shown(ReadKnowledge(character_id=taro, time="1200/01/01"))

    # 本人を知る相手から外すと、自分の芯を知らない(ミーム・行動原理は本人のもの)。関係のある相手の芯は、知る相手に入っていなければ分からない
    assert (result["自分"]["人物像"], result["自分"]["ミーム"]) == (None, "- 今表: 残るミーム")
    assert [(character["名前"], character["人物像"]) for character in result["知っている人物"]] == [("テスト花子", None)]
    ideas = [idea["名前"] for idea in result["知っているアイデア"]]
    assert "村の秘薬" in ideas and "遠い技" not in ideas


def test_read_appearance(shown, world):
    shown(UpdateCharacter(CharacterUpdateForm(id=world.character_ids[1], appearance="髪が赤い")))

    result = shown(ReadAppearance(character_id=world.character_ids[1], time="1200/01/01"))

    assert result == {"種別": "人物", "年齢": 30, "性別": "女", "背丈": 170.5, "体格": "細身", "外見": "髪が赤い"}


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
