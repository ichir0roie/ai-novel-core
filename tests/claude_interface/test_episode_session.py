"""本文・来歴を知る相手、人物が知ることのできるデータ(`character/read_knowledge`)と見た目(`read_appearance`)、
話のセッション(`episode_session/`)。"""
import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select

from ai.claude_code import ai_client
from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.delete_character import DeleteCharacter
from data_access_logic.character.form import (
    CharacterCreateForm, CharacterRelationUpdateForm, CharacterUpdateForm, KnowledgeChange, KnowledgeForm,
)
from data_access_logic.character.read_appearance import ReadAppearance
from data_access_logic.character.read_knowable_rows import ReadKnowableRows
from data_access_logic.character.read_known_rows import ReadKnownRows
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.read_known_ideas import ReadKnownIdeas
from data_access_logic.character.record import CharacterHistoryRow, CharacterParameterRow, CharacterRelationHistoryRow
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.update_character_relation import UpdateCharacterRelation
from data_access_logic.character.update_knowledge import UpdateKnowledge
from data_access_logic.episode.delete_episode import DeleteEpisode
from data_access_logic.episode.read_episode_brief import ReadEpisodeBrief
from data_access_logic.episode.voices import VoiceDraft, VoiceDrafts
from data_access_logic.episode_session.add_ideas import AddIdeas
from data_access_logic.episode_session.add_turns import AddTurns
from data_access_logic.episode_session.answer_turn import AnswerTurn
from data_access_logic.episode_session.clear_session import ClearSession
from data_access_logic.episode_session.close_session import CloseSession
from data_access_logic.episode_session.form import TurnAnswer, TurnRequest
from data_access_logic.episode_session.read_knower_gaps import ReadKnowerGaps
from data_access_logic.episode_session.read_played_turns import ReadPlayedTurns
from data_access_logic.episode_session.read_session import ReadSession
from data_access_logic.episode_session.read_session_since import ReadSessionSince
from data_access_logic.episode_session.read_stage import ReadStage
from data_access_logic.episode_session.read_turn import ReadTurn
from data_access_logic.idea.alias import called
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.models import IdeaDraft, IdeaDraftByAI, IdeaDraftsByAI
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.update_idea import UpdateIdea
from data_access_logic.knowers import KnowerRow
from db.schema import (
    Character, CharacterRelation, Episode, EpisodeCharacter, Idea, IdeaHistory, Stamp, get_env_session,
)
from tool import episode_session


def _histories(person: dict) -> list[str]:
    """「何年前、来歴」の一文から来歴だけを取る。"""
    return [history.split("、", 1)[1] for history in person["来歴(古い順)"]]


def _set_plot(world, plot_text: str) -> None:
    with get_env_session() as s:
        s.get_one(Episode, world.episode_id).plot_text = plot_text
        s.commit()


def _known_names(ideas: list[dict]) -> list[str]:
    return [name["呼び名"] for idea in ideas for name in idea["知っている呼び名"]]


def test_new_character_knows_its_history(shown):
    result = shown(CommitCharacter(CharacterCreateForm(
        name="知る人テスト", text="説明", histories=[CharacterHistoryRow(start=1195, description="市で店を開く")])))

    assert result["histories"][0]["knowers"] == [{"knower_id": result["id"], "location_id": None, "start": None}]


def test_knower_is_a_character_or_a_location(world):
    with pytest.raises(ValidationError, match="どちらか一方"):
        KnowerRow()
    with pytest.raises(ValidationError, match="どちらか一方"):
        KnowerRow(knower_id=world.character_ids[0], location_id=world.location_id)
    with pytest.raises(ValueError, match="knowers.knower_id"):
        UpdateCharacter(CharacterUpdateForm(id=world.character_ids[0], histories=[
            CharacterHistoryRow(start=1190, description="知る相手のいない行", knowers=[KnowerRow(knower_id=10**9)])])).run()


def test_delete_character_removes_its_knower_rows(shown, world):
    taro, _ = world.character_ids
    other = shown(CommitCharacter(CharacterCreateForm(name="消える人", text="説明")))
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="二人の秘密", knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=other["id"])])])))
    shown(DeleteCharacter(character_id=other["id"]))

    [row] = shown(ReadKnowableRows(character_id=taro))["character_histories"]
    # 知った時刻を渡さなければ、知る人物の生まれから知る
    assert row["knowers"] == [{"knower_id": taro, "location_id": None, "start": "1170/01/01 00:00:00"}]


def test_read_knowledge(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(
        id=taro, appearance="背が高い", text="太郎の芯", meme="- 今表: 太郎のミーム", principle="太郎の行動原理",
        plot="太郎の先の筋書き",
        histories=[CharacterHistoryRow(start=1190, description="太郎の秘密",
                                       knowers=[KnowerRow(knower_id=taro)])])))
    shown(UpdateCharacter(CharacterUpdateForm(
        id=hanako, appearance="髪が赤い", text="花子の芯", meme="- 裏: 花子のミーム", plot="花子の先",
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
        IdeaHistoryRow(location_id=world.neighbor_id, start="1150/01/01", name="村の隠し名",
                       knowers=[KnowerRow(knower_id=taro)]),
        # 始まりの空いた行と、話の時刻より後に始まる行は、知る相手に入っていても知らない
        IdeaHistoryRow(location_id=world.neighbor_id, name="いつからか分からない名", knowers=[KnowerRow(knower_id=taro)]),
        IdeaHistoryRow(location_id=world.neighbor_id, start="1250/01/01", name="先の名", knowers=[KnowerRow(knower_id=taro)]),
        # 効く場所に住んでいても、知る相手に入っていなければ知らない
        IdeaHistoryRow(location_id=world.location_id, name="都の知られない名"),
        IdeaHistoryRow(location_id=world.neighbor_id, name="誰も知らない名")])))
    _set_plot(world, "市でテスト術を見せる")

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
    assert result["自分"]["来歴(古い順)"] == ["10年前、市に越してくる", "今年、店を継ぐ"]
    relation = next(relation for relation in result["関係"] if relation["関係"] == "幼なじみ")
    assert relation["来歴(古い順)"] == ["5年前、市で再会する"]


def test_read_knowledge_at_the_latest_turn(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="市に越してくる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(start=1203, description="店を畳む", knowers=[KnowerRow(knower_id=taro)])])))
    shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, time="1203/05/01", request="三年が過ぎた"),
        TurnRequest(character_id=hanako, request="太郎が来た")]))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    assert result["自分"]["来歴(古い順)"] == ["13年前、市に越してくる", "今年、店を畳む"]


def test_read_knowledge_at_a_time_without_episode(shown, world):
    taro, _ = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="市に越してくる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(start=1203, description="店を畳む", knowers=[KnowerRow(knower_id=taro)])])))

    result = shown(ReadKnowledge(character_id=taro, time="1195/01/01"))

    assert result["自分"]["来歴(古い順)"] == ["5年前、市に越してくる"]
    # プロットが無いので、知っているアイデアは語から引くものだけ
    assert result["知っているアイデア"] == []
    with pytest.raises(ValueError):
        shown(ReadKnowledge(character_id=taro))


def test_read_knowledge_relation_histories_until_the_time(shown, world):
    shown(UpdateCharacterRelation(CharacterRelationUpdateForm(id=world.relation_id, histories=[
        CharacterRelationHistoryRow(start=1250, description="先に起きること"),
        CharacterRelationHistoryRow(start=1190, description="市で再会する"),
        CharacterRelationHistoryRow(description="年未定の構想")])))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=world.character_ids[0]))

    relation = next(relation for relation in result["関係"] if relation["関係"] == "幼なじみ")
    assert relation["説明"] == "同じ通りで育った"
    assert [history.split("、", 1)[1] for history in relation["来歴(古い順)"]] == ["市で再会する"]


def test_read_knowledge_leaves_out_undated_relations(shown, world):
    taro, _ = world.character_ids
    with get_env_session() as s:
        s.get_one(CharacterRelation, world.relation_id).start = None
        s.commit()

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    # いつからか決まっていない関係は、人物役にも語り部にも渡さない
    assert result["関係"] == [] and result["知っている人物"] == []
    assert shown(ReadStage(episode_id=world.episode_id))["知り合い"] == []


def test_location_knower_knows_from_the_start_of_the_row(shown, world, mock_ai):
    idea = shown(CommitIdea(IdeaCreateForm(name="都の祭", kind="風習", text="都の祭り", histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1180/06/01", name="灯祭",
                       knowers=[KnowerRow(location_id=world.location_id)])])))

    [row] = shown(ReadKnowableRows(idea_id=idea["id"]))["idea_histories"]

    # 知った時刻を渡さない場所の知る相手は、知られる行の始まりから知る
    assert row["knowers"] == [{"knower_id": None, "location_id": world.location_id, "start": "1180/06/01 00:00:00"}]


def test_read_knowledge_without_knowing(shown, world, mock_ai):
    taro, hanako = world.character_ids
    shown(CommitIdea(IdeaCreateForm(name="村の秘薬", kind="技術", text="村だけの薬", histories=[
        IdeaHistoryRow(location_id=world.neighbor_id, start="1150/01/01", name="秘薬",
                       knowers=[KnowerRow(knower_id=taro)])])))
    shown(CommitIdea(IdeaCreateForm(name="遠い技", kind="技術", text="村だけの技", histories=[
        IdeaHistoryRow(location_id=world.neighbor_id, name="遠い技")])))
    shown(CommitIdea(IdeaCreateForm(name="履歴の無い技", kind="技術", text="都の技")))

    _set_plot(world, "秘薬と遠い技と履歴の無い技")

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    # 芯は本人と関係のある人物が知る
    assert result["自分"]["人物像"] == "テスト太郎の説明"
    assert [(character["名前"], character["人物像"]) for character in result["知っている人物"]] == [("テスト花子", "テスト花子の説明")]
    # 履歴の行の知る相手に入っていれば知り、入っていなければ知らない。履歴の無いアイデアは住む場所に効いても知らない
    names = _known_names(result["知っているアイデア"])
    assert "秘薬" in names and "遠い技" not in names and "履歴の無い技" not in names


def test_read_knowledge_idea_history_only_by_knowers(shown, world, mock_ai):
    taro, hanako = world.character_ids
    idea = shown(CommitIdea(IdeaCreateForm(name="里の暦", kind="概念", text="里だけの数え方", histories=[
        IdeaHistoryRow(name="古い数え方", start="1150/01/01", detail="里では六千年台と記す",
                       knowers=[KnowerRow(knower_id=taro)])])))

    # 場所の空いた(どこでも効く)行でも、知る相手だけが知る
    def names(character_id: int) -> list[str]:
        [word] = shown(ReadKnownIdeas(episode_id=world.episode_id, character_id=character_id, words=["里の暦"]))
        return _known_names(word["知っているアイデア"])
    assert "古い数え方" in names(taro)
    assert "古い数え方" not in names(hanako)
    # 作中の呼び名は、知る相手に関わらず、場所・時代に効く行から選ぶ
    with get_env_session() as s:
        assert called(s, [idea["id"]], world.location_id, Stamp.parse("1200/01/01"))[idea["id"]].name == "古い数え方"

def test_update_knowledge(shown, world, mock_ai):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, histories=[
        CharacterHistoryRow(start=1191, description="花子の打ち明け話", knowers=[KnowerRow(knower_id=hanako)]),
        CharacterHistoryRow(start=1192, description="太郎が忘れる話", knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro)])])))
    idea = shown(CommitIdea(IdeaCreateForm(name="里の暗号", kind="概念", text="里だけの暗号", histories=[
        IdeaHistoryRow(name="符丁", detail="里の者だけが使う", knowers=[KnowerRow(knower_id=taro, start="1150/01/01")])])))
    rows = shown(ReadKnowableRows(character_id=hanako))
    told, forgotten = (row["id"] for row in rows["character_histories"])
    idea_row = shown(ReadKnowableRows(idea_id=idea["id"]))["idea_histories"][0]
    assert idea_row["name"] == "符丁"

    result = shown(UpdateKnowledge(KnowledgeForm(
        knower_id=taro,
        character_histories=[KnowledgeChange(id=told, known=True), KnowledgeChange(id=forgotten, known=False)],
        # 知る相手に入っている行は、知った時刻だけを直す
        idea_histories=[KnowledgeChange(id=idea_row["id"], known=True, start="1190/01/01")])))

    histories = [row["id"] for row in result["character_histories"]]
    assert told in histories and forgotten not in histories
    assert result == shown(ReadKnownRows(knower_id=taro))
    assert shown(ReadKnowableRows(idea_id=idea["id"]))["idea_histories"][0]["knowers"] == [
        {"knower_id": taro, "location_id": None, "start": "1190/01/01 00:00:00"}]
    knowledge = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))
    hanako_known = next(character for character in knowledge["知っている人物"] if character["名前"] == "テスト花子")
    assert _histories(hanako_known) == ["花子の打ち明け話"]


def test_read_knowable_rows_needs_one_source():
    with pytest.raises(ValueError):
        ReadKnowableRows()


def test_read_knowledge_only_ideas_in_the_plot(shown, world, mock_ai):
    taro, _ = world.character_ids
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="テスト術", detail="都での呼び名",
                       knowers=[KnowerRow(location_id=world.location_id)])])))
    shown(CommitIdea(IdeaCreateForm(name="テスト塩田", kind="施設", text="塩を作る浜", histories=[
        IdeaHistoryRow(location_id=world.location_id, name="塩の浜", detail="都の南の浜",
                       knowers=[KnowerRow(location_id=world.location_id)])])))
    _set_plot(world, "市でテスト術を見せる")

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    # 知っていても、プロットに名前の出ないアイデアは、はじめに読むデータに入れない(手番の要求に出たら語で引く)
    names = _known_names(result["知っているアイデア"])
    assert "テスト術" in names and "塩の浜" not in names


def test_read_known_ideas(shown, world, mock_ai):
    taro, _ = world.character_ids
    shown(CommitIdea(IdeaCreateForm(name="テスト塩田", kind="施設", text="塩を作る浜", histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="塩の浜", detail="都の南の浜",
                       knowers=[KnowerRow(location_id=world.location_id)])])))
    shown(CommitIdea(IdeaCreateForm(name="テスト泥鰻", kind="モンスター", text="水路の獣", histories=[
        IdeaHistoryRow(location_id=world.neighbor_id, name="テスト泥鰻", knowers=[KnowerRow(location_id=world.neighbor_id)])])))

    result = shown(ReadKnownIdeas(episode_id=world.episode_id, character_id=taro,
                                  words=["塩の浜の小屋", "テスト塩", "テスト泥鰻", "塩の浜の小屋"]))

    # 語が名前の一部か、名前が語の一部なら当たる。知らない語(知る相手の場所に住んでいない)は空。同じ語は一度だけ
    assert [word["語"] for word in result] == ["塩の浜の小屋", "テスト塩", "テスト泥鰻"]
    assert result[0]["知っているアイデア"] == [
        {"種別": "施設", "知っている呼び名": [{"呼び名": "塩の浜", "受け止め方": "都の南の浜"}]}]
    assert "塩の浜" in _known_names(result[1]["知っているアイデア"])
    assert result[2]["知っているアイデア"] == []
    assert "塩を作る浜" not in str(result)


def test_add_ideas(shown, world):
    result = shown(AddIdeas(episode_id=world.episode_id, ideas=[
        IdeaDraft(keyword="テスト追加語", description="市で売る干し菓子", kind="物品"),
        IdeaDraft(keyword="テスト魔導", description="都の技術", kind="技術"),
        IdeaDraft(keyword="テスト花子", description="人の名前", kind="呼称")]))

    # 当たらなかった語だけを候補として足し、既にある語と人名は足さない。アイデアの本文は返さない
    assert result == {"added": ["テスト追加語"], "kept": ["テスト魔導", "テスト花子"]}
    with get_env_session() as s:
        idea = s.scalars(select(Idea).where(Idea.name == "テスト追加語").order_by(Idea.id.desc())).first()
        assert idea is not None and (idea.kind, idea.text) == ("物品", "市で売る干し菓子")


def test_add_ideas_picks_a_kind_of_the_world(shown, world):
    # 星を表すアイデアがあれば、その下の分類の種別しか受けない(別の分類が増えないように)
    with get_env_session() as s:
        planet = Idea(name="テスト星の設定", kind="星", text="テスト用の星", histories=[IdeaHistory(location_id=world.planet_id, name="テスト星")])
        s.add(planet)
        s.flush()
        s.add(Idea(name="モンスター", kind="モンスター", text="分類", parent_idea_id=planet.id))
        s.commit()

    with pytest.raises(ValueError, match="種別は次から選ぶ: モンスター"):
        AddIdeas(episode_id=world.episode_id, ideas=[IdeaDraft(keyword="テスト泥鰻", kind="獣")]).run()
    assert shown(AddIdeas(episode_id=world.episode_id, ideas=[
        IdeaDraft(keyword="テスト泥鰻", description="水路の獣", kind="モンスター")]))["added"] == ["テスト泥鰻"]


# 花子の装いは 1190 年から木剣、1210 年から大剣(体格も変わる)
HANAKO_OUTFITS = [
    CharacterParameterRow(start="1170/01/01", sex="女", height=170.5, build="細身"),
    CharacterParameterRow(start="1190/01/01", outfit="腰に木剣"),
    CharacterParameterRow(start="1210/01/01", build="肩の厚い体", outfit="背に大剣")]


def test_read_appearance(shown, world):
    shown(UpdateCharacter(CharacterUpdateForm(id=world.character_ids[1], appearance="髪が赤い", parameters=HANAKO_OUTFITS)))

    result = shown(ReadAppearance(character_id=world.character_ids[1], time="1200/01/01"))
    later = shown(ReadAppearance(character_id=world.character_ids[1], time="1220/01/01"))

    # 体格・装いは、その時刻までに始まった一番新しい行の値
    assert result == {"種別": "人物", "年齢": 30, "性別": "女", "背丈": 170.5, "体格": "細身", "装い": "腰に木剣",
                      "外見": "髪が赤い"}
    assert (later["体格"], later["装い"]) == ("肩の厚い体", "背に大剣")


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


# 作者の目で読む材料には、来歴・履歴を知る相手に関わらずすべて渡し、話の時刻までに知った相手を添える。
# 話の時刻より後に始まる来歴・履歴と、後で知る相手は出さない
HANAKO_HISTORIES = [
    # 今ある行を書き換えた行なので、知る相手は今のまま(無い)
    {"時期": "1190/01/01", "来歴": "花子が店を開く", "知る相手": []},
    {"時期": "1195/01/01", "来歴": "花子の秘密",
     "知る相手": [{"人物": "テスト花子", "場所": None, "知った時刻": "1170/01/01 00:00:00"}]}]
IDEA_HISTORIES = [
    {"呼び名": "術の真名", "受け止め方": None, "効く場所": None, "始まり": None, "終わり": None,
     "知る相手": [{"人物": "テスト太郎", "場所": None, "知った時刻": "1170/01/01 00:00:00"}]},
    {"呼び名": "テスト術", "受け止め方": "都での呼び名", "効く場所": "テスト都", "始まり": "1150/01/01 00:00:00", "終わり": None,
     "知る相手": []}]
RELATIONS = [{"誰から": "テスト太郎", "誰へ": "テスト花子", "関係": "幼なじみ", "説明": "同じ通りで育った",
              "来歴(古い順)": [{"時期": "1195/01/01", "来歴": "市で再会する"}]}]


def test_read_stage(shown, world):
    _, hanako = world.character_ids
    _secrets(shown, world)
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, parameters=HANAKO_OUTFITS)))

    result = shown(ReadStage(episode_id=world.episode_id))

    assert result["この話"]["プロット"] == "市で出会う"
    assert result["場所(広い順)"] == ["テスト星", "テスト都"]
    assert result["場所の説明"] == "テスト用の都"
    # 語り部には人物の表層と知り合いの組だけを渡し、芯・来歴・関係の説明・設定は渡さない
    hanako_row = next(member for member in result["登場人物"] if member["人物id"] == hanako)
    assert hanako_row == {"人物id": hanako, "名前": "テスト花子", "年齢": hanako_row["年齢"], "性別": "女",
                          "体格": "細身", "装い": "腰に木剣", "外見": "髪が赤い"}
    assert result["知り合い"] == [{"誰から": "テスト太郎", "誰へ": "テスト花子", "関係": "幼なじみ"}]
    assert set(result) == {"この話", "場所(広い順)", "場所の説明", "場所の来歴(古い順)", "登場人物", "知り合い"}


def test_read_knower_gaps(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="テスト花子と市で会う", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(start=1191, description="テスト花子と組む",
                            knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=hanako, start="1191/01/01")]),
        # 話の時刻より後に知る行と、話の時刻より後に起きた行
        CharacterHistoryRow(start=1192, description="テスト花子に打ち明ける",
                            knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=hanako, start="1250/01/01")]),
        CharacterHistoryRow(start=1250, description="テスト花子と別れる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(description="テスト花子との先の構想")])))

    gaps = shown(ReadKnowerGaps(episode_id=world.episode_id))

    assert [(gap["character"]["id"], gap["description"], gap["unknowing"]) for gap in gaps] == [
        (taro, "テスト花子と市で会う", [{"id": hanako, "name": "テスト花子"}]),
        (taro, "テスト花子に打ち明ける", [{"id": hanako, "name": "テスト花子"}])]


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
    assert hanako_row["来歴(古い順)"] == HANAKO_HISTORIES
    assert episode["登場人物の関係"] == RELATIONS
    # 語はプロットと話のセッションの行から、元ごとに挙げる
    assert any("市で出会う" in prompt for prompt in sources)
    assert any("テスト術で灯をともす" in prompt for prompt in sources)
    ideas = {idea["アイデアid"]: idea for idea in episode["設定"]}
    idea = ideas[world.idea_id]
    assert idea["名前"] == "テスト術"
    assert idea["履歴(古い順)"] == IDEA_HISTORIES


def test_read_episode_brief_adjusts_voices(shown, world, mock_ai, monkeypatch):
    taro, hanako = world.character_ids
    with get_env_session() as s:
        s.add(Episode(story_id=world.story_id, title="前の話", plot_text="前", main_text="「よう」と太郎が笑った。",
                      start="1200/03/01 12:00:00", event_seeded=True))
        s.commit()
    prompts = []

    def generate(prompt, output, *args, **kwargs):
        if output is VoiceDrafts:
            prompts.append(prompt)
            return VoiceDrafts(voices=[
                VoiceDraft(character_id=taro, first_person="俺", second_person=None, third_person=None,
                           tone="砕けた短い言い切り", dialect=None),
                VoiceDraft(character_id=-1, first_person="誰か", second_person=None, third_person=None,
                           tone=None, dialect=None)])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    first = shown(ReadEpisodeBrief(episode_id=world.episode_id))
    shown(ReadEpisodeBrief(episode_id=world.episode_id))

    assert "よう" in prompts[0]
    with get_env_session() as s:
        rows = [row for row in s.get_one(Character, taro).parameters if row.start == Stamp.parse("1200/04/01 12:00:00")]
    # 同じ話の材料を読み直しても、調整の行は増えない。変わった欄だけを書き、ほかは前の行のまま
    assert [(row.first_person, row.tone, row.second_person) for row in rows] == [("俺", "砕けた短い言い切り", None)]
    member = next(member for member in first["この話"]["登場人物"] if member["人物id"] == taro)
    assert (member["一人称"], member["口調"], member["二人称"]) == ("俺", "砕けた短い言い切り", "あなた")
    assert "直前の話の本文(古い順)" in prompts[0]


def test_session_turns(shown, world):
    taro, hanako = world.character_ids
    added = shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, time="1200/04/01 12:00:00", request="市で花子を見かけた"),
        TurnRequest(character_id=hanako, request="太郎が手を振った")]))
    taro_turn, hanako_turn = (record["id"] for record in added)

    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "waiting"
    # 人物役には番の行の時刻を渡さない
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=taro))["record"] == {
        "id": taro_turn, "seen": [], "request": "市で花子を見かけた", "closing": False}
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


def test_narration_and_moves_reach_the_witnesses_once(shown, world):
    taro, hanako = world.character_ids
    narration, taro_turn = (record["id"] for record in shown(AddTurns(
        episode_id=world.episode_id, narration="市に鐘が鳴った", witness_ids=[taro, hanako],
        turns=[TurnRequest(character_id=taro, time="1200/04/01 12:00:00", request="鐘を聞いての一手")])))

    # 語りの行は手番に数えず、見聞きする人物の番に届く
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=taro))["record"] == {
        "id": taro_turn, "seen": ["市に鐘が鳴った"], "request": "鐘を聞いての一手", "closing": False}
    shown(AnswerTurn(record_id=taro_turn, answer=TurnAnswer(thought="花子だ", action="手を振る", speech="よう", aim="気づかせる")))
    [hanako_turn] = (record["id"] for record in shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=hanako, request="返事")], witness_ids=[taro])))
    # ほかの人物の一手は行動とセリフだけが名前付きで届き、内心・狙いは届かない
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["record"]["seen"] == [
        "市に鐘が鳴った", "テスト太郎: 手を振る「よう」"]
    shown(AnswerTurn(record_id=hanako_turn, answer=TurnAnswer(action="笑う")))
    [taro_next] = (record["id"] for record in shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, request="次の一手")])))
    # 前の番で受け取った語りと、自分の一手は届け直さない
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=taro))["record"]["seen"] == ["テスト花子: 笑う"]

    assert [played["seen"] for played in shown(ReadPlayedTurns(episode_id=world.episode_id, character_id=taro))] == [
        ["市に鐘が鳴った"]]
    records = shown(ReadSession(episode_id=world.episode_id))
    assert [(record["id"], record["character"]) for record in records][0] == (narration, None)
    assert [record["character_id"] for record in records[0]["witnesses"]] == [taro, hanako]
    assert records[0]["time"] == "1200/04/01 12:00:00"
    shown(CloseSession(episode_id=world.episode_id))
    assert [record["character"]["name"] for record in shown(ReadSession(episode_id=world.episode_id))
            if record["closing"]] == ["テスト太郎", "テスト花子"]
    assert shown(ClearSession(episode_id=world.episode_id, from_record_id=taro_next))["deleted"] == 3
    assert shown(ClearSession(episode_id=world.episode_id))["deleted"] == 3


def test_add_turns_checks_the_witnesses(shown, world):
    taro, hanako = world.character_ids
    stranger = shown(CommitCharacter(CharacterCreateForm(name="見知らぬ人", text="説明")))["id"]
    outsider = shown(CommitCharacter(CharacterCreateForm(name="話にいない人", text="説明")))["id"]
    with get_env_session() as s:
        s.add(EpisodeCharacter(episode_id=world.episode_id, character_id=stranger))
        s.commit()

    with pytest.raises(ValueError, match="知り合いでない"):
        AddTurns(episode_id=world.episode_id, witness_ids=[hanako, stranger],
                 turns=[TurnRequest(character_id=taro, request="一手")]).run()
    with pytest.raises(ValueError, match="登場人物でない"):
        AddTurns(episode_id=world.episode_id, witness_ids=[outsider],
                 turns=[TurnRequest(character_id=taro, request="一手")]).run()
    with pytest.raises(ValueError, match="witness_ids"):
        AddTurns(episode_id=world.episode_id, narration="鐘が鳴った", turns=[]).run()
    with pytest.raises(ValueError, match="turns か narration"):
        AddTurns(episode_id=world.episode_id, turns=[]).run()
    assert shown(ReadSession(episode_id=world.episode_id)) == []

    # 語りは知り合いでなくても届く。手番ごとの見聞きする人物は、語りの人物に代わる
    added = shown(AddTurns(episode_id=world.episode_id, narration="鐘が鳴った", witness_ids=[taro, hanako, stranger],
                           turns=[TurnRequest(character_id=taro, request="一手", witness_ids=[hanako])]))
    assert [[witness["character_id"] for witness in record["witnesses"]] for record in added] == [
        [taro, hanako, stranger], [hanako]]
    shown(DeleteCharacter(character_id=outsider))
    with get_env_session() as s:
        s.execute(delete(EpisodeCharacter).where(EpisodeCharacter.character_id == stranger))
        s.commit()
    shown(DeleteCharacter(character_id=stranger))
    [narration, _] = shown(ReadSession(episode_id=world.episode_id))
    assert [witness["character_id"] for witness in narration["witnesses"]] == [taro, hanako]


def test_wait_answers_returns_the_moves_without_the_requests(shown, world, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    narration, taro_turn = (record["id"] for record in shown(AddTurns(
        episode_id=world.episode_id, narration="市に鐘が鳴った", witness_ids=[taro, hanako],
        turns=[TurnRequest(character_id=taro, request="一手")])))

    assert episode_session.wait_answers(world.episode_id, narration - 1, interval=0.01, timeout=0.02) == {"status": "timeout"}
    shown(AnswerTurn(record_id=taro_turn, answer=TurnAnswer(thought="鐘だ", action="見上げる")))
    assert episode_session.wait_answers(world.episode_id, narration - 1, interval=0.01, timeout=0.02) == {
        "status": "answered",
        "answers": [{"id": taro_turn, "character": "テスト太郎", "thought": "鐘だ", "action": "見上げる", "speech": None,
                     "aim": None}]}
    assert episode_session._turns_args('[{"character_id": 1, "request": "一手"}]') == {
        "turns": [{"character_id": 1, "request": "一手"}]}
    assert episode_session._turns_args('{"narration": "鐘", "witness_ids": [1], "turns": []}') == {
        "narration": "鐘", "witness_ids": [1], "turns": []}


def test_clear_session_lets_the_actors_play_again(shown, world):
    taro, hanako = world.character_ids
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=taro, request="市に着いた")]))
    shown(CloseSession(episode_id=world.episode_id))
    # 一度も番の回らなかった登場人物の人物役も止まる
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "closed"

    assert shown(ClearSession(episode_id=world.episode_id)) == {"episode_id": world.episode_id, "deleted": 3}
    assert shown(ReadSession(episode_id=world.episode_id)) == []
    # 前の終了の行が消えたので、新しい手番が回る
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=hanako, request="市に着いた")]))
    assert shown(ReadTurn(episode_id=world.episode_id, character_id=hanako))["status"] == "turn"
    with pytest.raises(ValueError, match="episode_id"):
        ClearSession(episode_id=10**9).run()


def test_clear_session_from_a_record_replays_from_there(shown, world):
    taro, hanako = world.character_ids
    first, second, third = (record["id"] for record in shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, request="市に着いた"),
        TurnRequest(character_id=hanako, request="太郎が来た"),
        TurnRequest(character_id=taro, request="花子が笑った")])))
    shown(AnswerTurn(record_id=first, answer=TurnAnswer(thought="混んでいる", action="辺りを見回す", speech="さて")))
    shown(AnswerTurn(record_id=second, answer=TurnAnswer(action="笑う")))

    assert shown(ClearSession(episode_id=world.episode_id, from_record_id=second)) == {
        "episode_id": world.episode_id, "deleted": 2}
    assert [record["id"] for record in shown(ReadSession(episode_id=world.episode_id))] == [first]
    # 起こし直した人物役は、残った自分の手番だけを読む(時刻とほかの人物の行は入らない)
    assert shown(ReadPlayedTurns(episode_id=world.episode_id, character_id=taro)) == [{
        "id": first, "seen": [], "request": "市に着いた", "thought": "混んでいる", "action": "辺りを見回す", "speech": "さて",
        "aim": None}]
    assert shown(ReadPlayedTurns(episode_id=world.episode_id, character_id=hanako)) == []
    with pytest.raises(ValueError):
        ClearSession(episode_id=world.episode_id, from_record_id=third).run()


def test_read_session_since_returns_the_newer_rows(shown, world):
    taro, hanako = world.character_ids
    first, second = (record["id"] for record in shown(AddTurns(episode_id=world.episode_id, turns=[
        TurnRequest(character_id=taro, request="市に着いた"),
        TurnRequest(character_id=hanako, request="太郎が来た")])))

    assert [record["id"] for record in shown(ReadSessionSince(episode_id=world.episode_id))["records"]] == [first, second]
    assert shown(ReadSessionSince(episode_id=world.episode_id, after_record_id=second)) == {"records": [], "count": 2}
    # 一手が入った行も、その手前から引き直せば読める
    shown(AnswerTurn(record_id=first, answer=TurnAnswer(action="辺りを見回す")))
    since = shown(ReadSessionSince(episode_id=world.episode_id, after_record_id=first - 1))
    assert [(record["id"], record["action"]) for record in since["records"]] == [(first, "辺りを見回す"), (second, None)]


def test_wait_turn_returns_when_the_turn_comes(shown, world, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    shown(AddTurns(episode_id=world.episode_id, turns=[TurnRequest(character_id=taro, request="市に着いた")]))

    assert episode_session.wait_turn(world.episode_id, hanako, interval=0.01, timeout=0.02) == {"status": "timeout"}
    assert episode_session.wait_turn(world.episode_id, taro, interval=0.01, timeout=0.02)["status"] == "turn"
