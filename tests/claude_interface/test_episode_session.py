"""本文・来歴を知る相手、人物が知ることのできるデータ(`character/read_knowledge`)と見た目(`read_appearance`)、
話のセッション(`episode_session/`)。"""
import pytest
from pydantic import ValidationError

from ai.claude_code import ai_client
from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.delete_character import DeleteCharacter
from data_access_logic.character.form import CharacterCreateForm, CharacterRelationUpdateForm, CharacterUpdateForm
from data_access_logic.character.read_appearance import ReadAppearance
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.record import CharacterHistoryRow, CharacterRelationHistoryRow
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.update_character_relation import UpdateCharacterRelation
from data_access_logic.episode.delete_episode import DeleteEpisode
from data_access_logic.episode.read_episode_brief import ReadEpisodeBrief
from data_access_logic.episode_session.add_turns import AddTurns
from data_access_logic.episode_session.answer_turn import AnswerTurn
from data_access_logic.episode_session.clear_session import ClearSession
from data_access_logic.episode_session.close_session import CloseSession
from data_access_logic.episode_session.form import TurnAnswer, TurnRequest
from data_access_logic.episode_session.read_session import ReadSession
from data_access_logic.episode_session.read_stage import ReadStage
from data_access_logic.episode_session.read_turn import ReadTurn
from data_access_logic.idea.alias import called
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.models import IdeaDraftByAI, IdeaDraftsByAI
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.update_idea import UpdateIdea
from data_access_logic.knowers import KnowerRow
from db.schema import Stamp, get_env_session
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

    assert shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))["自分"]["人物像"] == "テスト太郎の説明"


def test_read_knowledge(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(
        id=taro, appearance="背が高い", text="太郎の芯", meme="- 今表: 太郎のミーム", principle="太郎の行動原理",
        plot="太郎の先の筋書き",
        histories=[CharacterHistoryRow(start=1190, description="太郎の秘密",
                                       knowers=[KnowerRow(knower_id=taro)])])))
    shown(UpdateCharacter(CharacterUpdateForm(
        id=hanako, appearance="髪が赤い", text="花子の芯", meme="- 裏: 花子のミーム", plot="花子の先",
        knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro, start="1195/01/01")],
        histories=[
            CharacterHistoryRow(start=1190, description="都の噂",
                                knowers=[KnowerRow(location_id=world.location_id)]),
            CharacterHistoryRow(start=1191, description="花子だけの秘密", knowers=[KnowerRow(knower_id=hanako)]),
            CharacterHistoryRow(start=1192, description="太郎も知る秘密",
                                knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro, start="1199/01/01")]),
            CharacterHistoryRow(start=1193, description="後で知る秘密",
                                knowers=[KnowerRow(knower_id=taro, start="1201/01/01")]),
            # 関係のある人物でも、知る相手に入っていなければ知らない
            CharacterHistoryRow(start=1194, description="花子が店を開く", knowers=[KnowerRow(knower_id=hanako)]),
            CharacterHistoryRow(start=1250, description="先のこと", knowers=[KnowerRow(location_id=world.location_id)])])))
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="テスト術", detail="都での呼び名",
                       knowers=[KnowerRow(location_id=world.location_id, start="1150/01/01")]),
        IdeaHistoryRow(location_id=world.neighbor_id, name="村の隠し名", knowers=[KnowerRow(knower_id=taro)]),
        # 効く場所に住んでいても、知る相手に入っていなければ知らない
        IdeaHistoryRow(location_id=world.location_id, name="都の知られない名"),
        IdeaHistoryRow(location_id=world.neighbor_id, name="誰も知らない名")])))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    me = result["自分"]
    assert (me["外見"], me["人物像"], me["ミーム"], me["行動原理"]) == ("背が高い", "太郎の芯", "- 今表: 太郎のミーム", "太郎の行動原理")
    assert "筋書き" not in me
    assert _histories(me) == ["太郎の秘密"]
    hanako_known = next(character for character in result["知っている人物"] if character["名前"] == "テスト花子")
    assert (hanako_known["外見"], hanako_known["人物像"]) == ("髪が赤い", "花子の芯")
    assert "ミーム" not in hanako_known
    assert _histories(hanako_known) == ["都の噂", "太郎も知る秘密"]
    # アイデアの本文と本質の名前は渡さず、知っている履歴の行(呼び名と受け止め方)だけを渡す
    idea = next(idea for idea in result["知っているアイデア"]
                if "テスト術" in [name["呼び名"] for name in idea["知っている呼び名"]])
    assert set(idea) == {"種別", "知っている呼び名"}
    assert idea["知っている呼び名"] == [{"呼び名": "テスト術", "受け止め方": "都での呼び名"},
                                 {"呼び名": "村の隠し名", "受け止め方": None}]
    assert "テスト用の技術" not in str(result["知っているアイデア"])


def test_read_knowledge_tells_years_ago_instead_of_years(shown, world):
    taro, _ = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="市に越してくる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(start=1200, description="店を継ぐ", knowers=[KnowerRow(knower_id=taro)])])))
    shown(UpdateCharacterRelation(CharacterRelationUpdateForm(id=world.relation_id, histories=[
        CharacterRelationHistoryRow(start=1195, description="市で再会する")])))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    assert "時刻" not in result
    assert result["自分"]["来歴(古い順)"] == [{"いつ": "10年前", "来歴": "市に越してくる"}, {"いつ": "今年", "来歴": "店を継ぐ"}]
    relation = next(relation for relation in result["関係"] if relation["関係"] == "幼なじみ")
    assert relation["来歴(古い順)"] == [{"いつ": "5年前", "来歴": "市で再会する"}]


def test_read_knowledge_at_the_latest_turn(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="市に越してくる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(start=1203, description="店を畳む", knowers=[KnowerRow(knower_id=taro)])])))
    shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, time="1203/05/01", request="三年が過ぎた"),
        TurnRequest(character_id=hanako, request="太郎が来た")]))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    assert result["自分"]["来歴(古い順)"] == [{"いつ": "13年前", "来歴": "市に越してくる"}, {"いつ": "今年", "来歴": "店を畳む"}]


def test_read_knowledge_relation_histories_until_the_time(shown, world):
    shown(UpdateCharacterRelation(CharacterRelationUpdateForm(id=world.relation_id, histories=[
        CharacterRelationHistoryRow(start=1250, description="先に起きること"),
        CharacterRelationHistoryRow(start=1190, description="市で再会する"),
        CharacterRelationHistoryRow(description="年未定の構想")])))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=world.character_ids[0]))

    relation = next(relation for relation in result["関係"] if relation["関係"] == "幼なじみ")
    assert relation["説明"] == "同じ通りで育った"
    assert [history["来歴"] for history in relation["来歴(古い順)"]] == ["市で再会する"]


def test_read_knowledge_without_knowing(shown, world, mock_ai):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, meme="- 今表: 残るミーム", knowers=[])))
    shown(CommitIdea(IdeaCreateForm(name="村の秘薬", kind="技術", text="村だけの薬", histories=[
        IdeaHistoryRow(location_id=world.neighbor_id, name="秘薬", knowers=[KnowerRow(knower_id=taro)])])))
    shown(CommitIdea(IdeaCreateForm(name="遠い技", kind="技術", text="村だけの技", histories=[
        IdeaHistoryRow(location_id=world.neighbor_id, name="遠い技")])))
    shown(CommitIdea(IdeaCreateForm(name="履歴の無い技", kind="技術", text="都の技")))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    # 本人を知る相手から外すと、自分の芯を知らない(ミーム・行動原理は本人のもの)。関係のある相手の芯は、知る相手に入っていなければ分からない
    assert (result["自分"]["人物像"], result["自分"]["ミーム"]) == (None, "- 今表: 残るミーム")
    assert [(character["名前"], character["人物像"]) for character in result["知っている人物"]] == [("テスト花子", None)]
    # 履歴の行の知る相手に入っていれば知り、入っていなければ知らない。履歴の無いアイデアは住む場所に効いても知らない
    names = [name["呼び名"] for idea in result["知っているアイデア"] for name in idea["知っている呼び名"]]
    assert "秘薬" in names and "遠い技" not in names and "履歴の無い技" not in names


def test_read_knowledge_idea_history_only_by_knowers(shown, world, mock_ai):
    taro, hanako = world.character_ids
    idea = shown(CommitIdea(IdeaCreateForm(name="里の暦", kind="概念", text="里だけの数え方", histories=[
        IdeaHistoryRow(name="古い数え方", detail="里では六千年台と記す", knowers=[KnowerRow(knower_id=taro)])])))

    # 場所も期間も空の(どこでも効く)行でも、知る相手だけが知る
    def names(character_id: int) -> list[str]:
        result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=character_id))
        return [name["呼び名"] for known in result["知っているアイデア"] for name in known["知っている呼び名"]]
    assert "古い数え方" in names(taro)
    assert "古い数え方" not in names(hanako)
    # 作中の呼び名は、知る相手に関わらず、場所・時代に効く行から選ぶ
    with get_env_session() as s:
        assert called(s, [idea["id"]], world.location_id, Stamp.parse("1200/01/01"))[idea["id"]].name == "古い数え方"

def test_read_appearance(shown, world):
    shown(UpdateCharacter(CharacterUpdateForm(id=world.character_ids[1], appearance="髪が赤い")))

    result = shown(ReadAppearance(character_id=world.character_ids[1], time="1200/01/01"))

    assert result == {"種別": "人物", "年齢": 30, "性別": "女", "背丈": 170.5, "体格": "細身", "外見": "髪が赤い"}


def test_read_knowledge_skips_unrelated_cast(shown, world):
    stranger = shown(CommitCharacter(CharacterCreateForm(name="初対面の人", text="説明")))
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=stranger["id"], request="市に着いた")]))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=world.character_ids[0]))

    assert "初対面の人" not in [character["名前"] for character in result["知っている人物"]]


def _secrets(shown, world) -> None:
    """花子に知る相手の違う来歴を、関係に来歴を、アイデアに知る相手の違う履歴を足す(話の時刻は 1200 年)。"""
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(
        id=hanako, appearance="髪が赤い",
        knowers=[KnowerRow(knower_id=hanako), KnowerRow(location_id=world.location_id, start="1195/01/01")],
        histories=[
            CharacterHistoryRow(start=1190, description="花子が店を開く"),
            CharacterHistoryRow(start=1195, description="花子の秘密",
                                knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro, start="1201/01/01")]),
            CharacterHistoryRow(start=1250, description="先のこと")])))
    shown(UpdateCharacterRelation(CharacterRelationUpdateForm(id=world.relation_id, histories=[
        CharacterRelationHistoryRow(start=1195, description="市で再会する")])))
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="テスト術", detail="都での呼び名"),
        IdeaHistoryRow(name="術の真名", knowers=[KnowerRow(knower_id=taro)]),
        IdeaHistoryRow(start="1300/01/01", name="先の呼び名")])))


# 作者の目で読む材料には、芯・来歴・履歴を知る相手に関わらずすべて渡し、話の時刻までに知った相手を添える。
# 話の時刻より後に始まる来歴・履歴と、後で知る相手は出さない
HANAKO_KNOWERS = [{"人物": "テスト花子", "場所": None, "知った時刻": None},
                  {"人物": None, "場所": "テスト都", "知った時刻": "1195/01/01 00:00:00"}]
HANAKO_HISTORIES = [
    # 今ある行を書き換えた行なので、知る相手は今のまま(無い)
    {"年": 1190, "来歴": "花子が店を開く", "知る相手": []},
    {"年": 1195, "来歴": "花子の秘密",
     "知る相手": [{"人物": "テスト花子", "場所": None, "知った時刻": None}]}]
IDEA_HISTORIES = [
    {"呼び名": "術の真名", "受け止め方": None, "効く場所": None, "始まり": None, "終わり": None,
     "知る相手": [{"人物": "テスト太郎", "場所": None, "知った時刻": None}]},
    {"呼び名": "テスト術", "受け止め方": "都での呼び名", "効く場所": "テスト都", "始まり": "1150/01/01 00:00:00", "終わり": None,
     "知る相手": []}]
RELATIONS = [{"誰から": "テスト太郎", "誰へ": "テスト花子", "関係": "幼なじみ", "説明": "同じ通りで育った",
              "来歴(古い順)": [{"年": 1195, "来歴": "市で再会する"}]}]


def test_read_stage(shown, world):
    _, hanako = world.character_ids
    _secrets(shown, world)

    result = shown(ReadStage(episode_id=world.episode_id))

    assert result["この話"]["プロット"] == "市で出会う"
    assert result["場所(広い順)"] == ["テスト星", "テスト都"]
    assert result["場所の説明"] == "テスト用の都"
    # 語り部には人物の表層と知り合いの組だけを渡し、芯・来歴・関係の説明・設定は渡さない
    hanako_row = next(member for member in result["登場人物"] if member["人物id"] == hanako)
    assert hanako_row == {"人物id": hanako, "名前": "テスト花子", "年齢": hanako_row["年齢"], "性別": "女",
                          "外見": "髪が赤い"}
    assert result["知り合い"] == [{"誰から": "テスト太郎", "誰へ": "テスト花子", "関係": "幼なじみ"}]
    assert set(result) == {"この話", "場所(広い順)", "場所の説明", "登場人物", "知り合い"}


def test_read_episode_brief(shown, world, mock_ai, monkeypatch):
    taro, hanako = world.character_ids
    _secrets(shown, world)
    [turn] = shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=taro, request="日が暮れた")]))
    shown(AnswerTurn(record_id=turn["id"], answer=TurnAnswer(action="テスト術で灯をともす")))
    sources = []

    def generate(prompt, output, *args, **kwargs):
        # 設定の語は、話のセッションの行に出た語だけを挙げたことにする
        if output is IdeaDraftsByAI:
            sources.append(prompt)
            return output(ideas=[IdeaDraftByAI(keyword="テスト術", variants=[], description="灯をともす術", coined=True,
                                               kind="技術", start=None, end=None)] if "テスト術" in prompt else [])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    result = shown(ReadEpisodeBrief(episode_id=world.episode_id))

    episode = result["この話"]
    hanako_row = next(member for member in episode["登場人物"] if member["人物id"] == hanako)
    assert (hanako_row["人物像を知る相手"], hanako_row["来歴(古い順)"]) == (HANAKO_KNOWERS, HANAKO_HISTORIES)
    assert episode["登場人物の関係"] == RELATIONS
    # 語はプロットと話のセッションの行から、元ごとに挙げる
    assert any("市で出会う" in prompt for prompt in sources)
    assert any("テスト術で灯をともす" in prompt for prompt in sources)
    ideas = {idea["アイデアid"]: idea for idea in episode["設定"]}
    idea = ideas[world.idea_id]
    assert idea["名前"] == "テスト術"
    assert idea["履歴(古い順)"] == IDEA_HISTORIES


def test_session_turns(shown, world):
    taro, hanako = world.character_ids
    added = shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, time="1200/04/01 12:00:00", request="市で花子を見かけた"),
        TurnRequest(character_id=hanako, request="太郎が手を振った")]))
    taro_turn, hanako_turn = (record["id"] for record in added)

    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "waiting"
    # 人物役には番の行の時刻を渡さない
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=taro))["record"] == {
        "id": taro_turn, "request": "市で花子を見かけた", "closing": False}
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


def test_clear_session_lets_the_actors_play_again(shown, world):
    taro, hanako = world.character_ids
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=taro, request="市に着いた")]))
    shown(CloseSession(episode_id=world.episode_id))

    assert shown(ClearSession(episode_id=world.episode_id)) == {"episode_id": world.episode_id, "deleted": 2}
    assert shown(ReadSession(episode_id=world.episode_id)) == []
    # 前の終了の行が消えたので、新しい手番が回る
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=hanako, request="市に着いた")]))
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "turn"
    with pytest.raises(ValueError, match="episode_id"):
        ClearSession(episode_id=10**9).run()


def test_wait_turn_returns_when_the_turn_comes(shown, world, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=taro, request="市に着いた")]))

    assert episode_session.wait_turn(world.episode_id, hanako, interval=0.01, timeout=0.02) == {"status": "timeout"}
    assert episode_session.wait_turn(world.episode_id, taro, interval=0.01, timeout=0.02)["status"] == "turn"
