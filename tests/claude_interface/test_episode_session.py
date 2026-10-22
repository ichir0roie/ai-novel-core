"""本文・来歴を知る相手、人物が知ることのできるデータ(`character/read_knowledge`)と見た目(`read_appearance`)、
話のセッション(`episode_session/`)。"""
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from ai.claude_code import ai_client
from data_access_logic import constants
from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.commit_character_relation import CommitCharacterRelation
from data_access_logic.character.delete_character import DeleteCharacter
from data_access_logic.character.form import (
    CharacterCreateForm, CharacterRelationCreateForm, CharacterRelationUpdateForm, CharacterSkillCreateForm, CharacterUpdateForm,
    KnowledgeChange, KnowledgeForm,
)
from data_access_logic.character.read_appearance import ReadAppearance
from data_access_logic.character.read_knowable_rows import ReadKnowableRows
from data_access_logic.character.read_known_rows import ReadKnownRows
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.read_known_ideas import ReadKnownIdeas
from data_access_logic.character.commit_character_skill import CommitCharacterSkill
from data_access_logic.character.record import (
    CharacterHistoryRow, CharacterParameterRow, CharacterRelationHistoryRow, CharacterSkillHistoryRow,
)
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.update_character_relation import UpdateCharacterRelation
from data_access_logic.character.update_knowledge import UpdateKnowledge
from data_access_logic.episode.read_character_episodes import ReadCharacterEpisodes
from data_access_logic.episode.read_episode_brief import ReadEpisodeBrief
from data_access_logic.episode.read_episode_casting import ReadEpisodeCasting
from data_access_logic.episode.refresh_voices import RefreshVoices
from data_access_logic.episode.voices import VoiceDraft, VoiceDrafts
from data_access_logic.episode_session import store
from data_access_logic.episode_session.add_ideas import AddIdeas
from data_access_logic.episode_session.append_text import AppendText
from data_access_logic.episode_session.read_knower_gaps import ReadKnowerGaps
from data_access_logic.episode_session.read_stage import ReadStage
from data_access_logic.episode_session.replace_text import ReplaceText
from data_access_logic.episode_session.store import SessionStore
from data_access_logic.idea.alias import called
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.models import IdeaDraft, IdeaDraftByAI, IdeaDraftsByAI
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.update_idea import UpdateIdea
from data_access_logic.knowers import KnowerRow
from db.schema import (
    PERSONALITY_LEVELS, Character, CharacterParameter, CharacterRelation, Episode, EpisodeCharacter, Idea, IdeaHistory, Stamp,
    get_env_session,
)
from tool import episode_session


@pytest.fixture(autouse=True)
def session_root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """手番のファイルを、テストごとの空の場所に置く(手元の `.cache` に書かない)。"""
    monkeypatch.setattr(store, "ROOT", tmp_path / "episode_session")


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
    # 性格は本人にだけ渡す
    assert len(me["性格"]) == 12 and me["性格"]["誠実性"] in PERSONALITY_LEVELS
    assert _histories(me) == ["太郎の秘密"]
    hanako_known = next(character for character in result["知っている人物"] if character["名前"] == "テスト花子")
    assert (hanako_known["外見"], hanako_known["人物像"]) == ("髪が赤い", "花子の芯")
    assert "ミーム" not in hanako_known and "性格" not in hanako_known
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


def test_read_knowledge_at_the_latest_turn(shown, world, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="市に越してくる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(start=1203, description="店を畳む", knowers=[KnowerRow(knower_id=taro)])])))
    session = SessionStore(world.episode_id)
    episode_session.stage(session)
    session.add({"witness_ids": [], "turns": [{"character_id": taro, "time": "1203/05/01", "request": "三年が過ぎた"},
                                              {"character_id": hanako, "request": "太郎が来た"}]})

    # 人物役には時刻を渡さないので、手番のファイルにあるその人物の一番新しい手番の時刻で読む
    moment = episode_session._knowing(world.episode_id, taro, None)
    assert moment == {"episode_id": world.episode_id, "time": "1203/05/01"}
    result = shown(ReadKnowledge(character_id=taro, **moment))
    assert result["自分"]["来歴(古い順)"] == ["13年前、市に越してくる", "今年、店を畳む"]
    # 時刻の入った手番の無い人物は、話の時刻で読む
    assert episode_session._knowing(world.episode_id, hanako, None) == {"episode_id": world.episode_id}


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


# 花子は 1210 年から体格が変わる
HANAKO_PARAMETERS = [
    CharacterParameterRow(start="1170/01/01", sex="女", height=170.5, build="細身"),
    CharacterParameterRow(start="1210/01/01", build="肩の厚い体")]
# 花子の装いは 1191 年から 1210 年まで木剣、1192 年から外套(1205 年に裾が焦げる)、1210 年から大剣
HANAKO_OUTFITS = {
    "木剣": [CharacterSkillHistoryRow(start="1191/01/01", end="1210/01/01", description="腰に木剣")],
    "外套": [CharacterSkillHistoryRow(start="1192/01/01", end="1205/01/01", description="灰色の外套"),
             CharacterSkillHistoryRow(start="1205/01/01", description="裾の焦げた灰色の外套")],
    "大剣": [CharacterSkillHistoryRow(start="1210/01/01", description="背に大剣")]}
# 袋の短刀は本人だけが知る
# (1190 年には `world` の来歴の行があり、始まりの同じ行は今ある行を使い回して知る相手を引き継ぐので、年をずらす)
HANAKO_SECRETS = [CharacterHistoryRow(start="1195/01/01", kind="隠し事", description="袋に短刀")]


def _dress(shown, character_id: int) -> None:
    for name, histories in HANAKO_OUTFITS.items():
        shown(CommitCharacterSkill(CharacterSkillCreateForm(
            character_id=character_id, name=name, kind="装い", histories=histories)))


def test_read_appearance(shown, world):
    shown(UpdateCharacter(CharacterUpdateForm(
        id=world.character_ids[1], appearance="髪が赤い", parameters=HANAKO_PARAMETERS)))
    _dress(shown, world.character_ids[1])

    result = shown(ReadAppearance(character_id=world.character_ids[1], time="1200/01/01"))
    later = shown(ReadAppearance(character_id=world.character_ids[1], time="1220/01/01"))
    before = shown(ReadAppearance(character_id=world.character_ids[1], time="1180/01/01"))

    # 体格は、その時刻までに始まった一番新しい行の値。装いは、身に着けている物ごとに、その時刻に効いている来歴の行の文
    assert result == {"種別": "人物", "年齢": 30, "性別": "女", "背丈": 170.5, "体格": "細身",
                      "装い": ["腰に木剣", "灰色の外套"], "外見": "髪が赤い"}
    # 終わり(`end`)の時刻からは、その来歴の行は効かない(物を手放した・移り変わった)
    assert (later["体格"], later["装い"]) == ("肩の厚い体", ["裾の焦げた灰色の外套", "背に大剣"])
    assert before["装い"] == []


def test_read_knowledge_tells_kind_of_histories(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, histories=HANAKO_SECRETS)))
    _dress(shown, hanako)

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=hanako))
    others = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    # 種別の行は種別を頭に付けて渡し、隠し事は知る相手(本人)だけが知る。装いは見た目にだけ入れ、スキルには入れない
    assert result["自分"]["来歴(古い順)"] == ["5年前、隠し事: 袋に短刀"]
    assert result["自分"]["装い"] == ["腰に木剣", "灰色の外套"]
    assert result["自分"]["スキル"] == []
    known = next(character for character in others["知っている人物"] if character["名前"] == "テスト花子")
    assert "5年前、隠し事: 袋に短刀" not in known["来歴(古い順)"]
    assert known["装い"] == ["腰に木剣", "灰色の外套"]


def test_read_knowledge_skips_unrelated_cast(shown, world):
    shown(CommitCharacter(CharacterCreateForm(name="初対面の人", text="説明")))

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=world.character_ids[0]))

    assert "初対面の人" not in [character["名前"] for character in result["知っている人物"]]


def _secrets(shown, world) -> None:
    """花子に知る相手の違う来歴を、アイデアに知る相手の違う履歴を足す(話の時刻は 1200 年)。"""
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(
        id=hanako, appearance="髪が赤い",
        histories=[
            CharacterHistoryRow(start=1190, description="花子が店を開く"),
            CharacterHistoryRow(start=1195, description="花子の秘密",
                                knowers=[KnowerRow(knower_id=hanako), KnowerRow(knower_id=taro, start="1201/01/01")]),
            CharacterHistoryRow(start=1250, description="先のこと")])))
    shown(UpdateIdea(IdeaUpdateForm(id=world.idea_id, histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="テスト術", detail="都での呼び名"),
        IdeaHistoryRow(name="術の真名", knowers=[KnowerRow(knower_id=taro)]),
        IdeaHistoryRow(start="1300/01/01", name="先の呼び名")])))


# 作者の目で読む材料には、来歴・履歴を知る相手に関わらずすべて渡し、知る相手が人物に限られた行には、
# 話の時刻までに知った人物を「秘密」として添える。話の時刻より後に始まる来歴・履歴と、後で知る相手は出さない
HANAKO_HISTORIES = [
    # 今ある行を書き換えた行なので、知る相手は今のまま(無い)
    {"種別": None, "時期": "1190/01/01", "来歴": "花子が店を開く", "秘密": "作中の誰も知らない"},
    {"種別": None, "時期": "1195/01/01", "来歴": "花子の秘密", "秘密": "テスト花子だけが知る"}]
IDEA_HISTORIES = [
    {"呼び名": "術の真名", "受け止め方": None, "効く場所": None, "始まり": None, "終わり": None, "秘密": "テスト太郎だけが知る"},
    {"呼び名": "テスト術", "受け止め方": "都での呼び名", "効く場所": "テスト都", "始まり": "1150/01/01 00:00:00", "終わり": None,
     "秘密": "作中の誰も知らない"}]


def test_read_stage(shown, world):
    _, hanako = world.character_ids
    _secrets(shown, world)
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, parameters=HANAKO_PARAMETERS)))
    _dress(shown, hanako)

    result = shown(ReadStage(episode_id=world.episode_id))

    assert result["この話"]["プロット"] == "市で出会う"
    assert result["場所(広い順)"] == ["テスト星", "テスト都"]
    assert result["場所の説明"] == "テスト用の都"
    # 語り部には人物の表層と知り合いの組だけを渡し、芯・来歴・関係の説明・設定は渡さない
    hanako_row = next(member for member in result["登場人物"] if member["人物id"] == hanako)
    assert hanako_row == {"人物id": hanako, "名前": "テスト花子", "年齢": hanako_row["年齢"], "性別": "女",
                          "体格": "細身", "装い": ["腰に木剣", "灰色の外套"], "外見": "髪が赤い"}
    taro, _ = world.character_ids
    assert result["知り合い"] == [{"人物id": [taro, hanako], "誰から": "テスト太郎", "誰へ": "テスト花子", "関係": "幼なじみ"}]
    assert set(result) == {"この話", "場所(広い順)", "場所の説明", "場所の来歴(古い順)", "登場人物", "知り合い"}


def test_read_knower_gaps(shown, world):
    taro, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=taro, histories=[
        CharacterHistoryRow(start=1190, description="テスト花子と市で会う", knowers=[KnowerRow(knower_id=taro)]),
        # 同じ出来事のうち、テスト花子が知るはずの所だけを分けた行
        CharacterHistoryRow(start=1190, description="市で会って名乗り合う",
                            knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=hanako, start="1190/01/01")]),
        CharacterHistoryRow(start=1191, description="テスト花子と組む",
                            knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=hanako, start="1191/01/01")]),
        # 話の時刻より後に知る行と、話の時刻より後に起きた行
        CharacterHistoryRow(start=1192, description="テスト花子に打ち明ける",
                            knowers=[KnowerRow(knower_id=taro), KnowerRow(knower_id=hanako, start="1250/01/01")]),
        CharacterHistoryRow(start=1250, description="テスト花子と別れる", knowers=[KnowerRow(knower_id=taro)]),
        CharacterHistoryRow(description="テスト花子との先の構想")])))

    gaps = shown(ReadKnowerGaps(episode_id=world.episode_id))

    hanako_named = {"id": hanako, "name": "テスト花子"}
    assert [(gap["character"]["id"], gap["description"], gap["unknowing"]) for gap in gaps] == [
        (taro, "テスト花子と市で会う", [hanako_named]),
        (taro, "テスト花子に打ち明ける", [hanako_named])]
    # 同じ始まりで、抜けた人物がもう知っている行を添える
    assert [(cover["description"], cover["knowing"]) for cover in gaps[0]["covered_by"]] == [
        ("市で会って名乗り合う", [hanako_named])]
    assert gaps[1]["covered_by"] == []


def test_read_episode_brief(shown, world, mock_ai, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    _secrets(shown, world)
    session = SessionStore(world.episode_id)
    episode_session.stage(session)
    [turn] = session.add({"witness_ids": [], "turns": [{"character_id": taro, "request": "日が暮れた"}]})
    session.answer(turn.id, {"action": "テスト術で灯をともす"})
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
    # 本文を書く材料には、話の時刻より先の筋(筋書き)・関わった話・関係を渡さない
    assert "筋書き" not in hanako_row
    assert not {"関わった話(古い順)", "登場人物の関係"} & set(episode)
    # 語はプロットと話のセッションの行から、元ごとに挙げる
    assert any("市で出会う" in prompt for prompt in sources)
    assert any("テスト術で灯をともす" in prompt for prompt in sources)
    ideas = {idea["アイデアid"]: idea for idea in episode["設定"]}
    idea = ideas[world.idea_id]
    assert idea["名前"] == "テスト術"
    assert idea["履歴(古い順)"] == IDEA_HISTORIES


def test_read_episode_brief_style_samples(shown, world, mock_ai, monkeypatch):
    with get_env_session() as s:
        for title, start, text in [("一番古い話", "1200/02/01 12:00:00", "一番古い話の本文。"),
                                   ("その前の話", "1200/02/15 12:00:00", "その前の話の本文。"),
                                   ("前の話", "1200/03/01 12:00:00", "前の話。\n続き。")]:
            s.add(Episode(story_id=world.story_id, title=title, plot_text=title, main_text=text, start=start))
        s.commit()

    def samples(letters):
        monkeypatch.setattr(constants, "EPISODE_STYLE_SAMPLE_LETTERS", letters)
        return shown(ReadEpisodeBrief(episode_id=world.episode_id))["文体の見本(古い順)"]

    # 新しい話から、まるごと収まるだけ。収まらない話で止め、それより古い話は見ない
    assert samples(20) == ["その前の話の本文。", "前の話。\n続き。"]
    assert samples(10) == ["前の話。\n続き。"]
    # 直前の話だけで上限を超えるときは、収まる行まで
    assert samples(6) == ["前の話。"]


def test_read_episode_brief_does_not_adjust_voices(shown, world, mock_ai, monkeypatch):
    with get_env_session() as s:
        s.add(Episode(story_id=world.story_id, title="前の話", plot_text="前", main_text="「よう」と太郎が笑った。",
                      start="1200/03/01 12:00:00"))
        s.commit()
    asked = []

    def generate(prompt, output, *args, **kwargs):
        asked.append(output)
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    shown(ReadEpisodeBrief(episode_id=world.episode_id))

    assert VoiceDrafts not in asked


def test_refresh_voices(shown, world, mock_ai, monkeypatch):
    taro, hanako = world.character_ids
    with get_env_session() as s:
        s.add(Episode(story_id=world.story_id, title="前の話", plot_text="前", main_text="「よう」と太郎が笑った。",
                      start="1200/03/01 12:00:00"))
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

    adjusted = shown(RefreshVoices(episode_id=world.episode_id))
    again = shown(RefreshVoices(episode_id=world.episode_id))
    first = shown(ReadEpisodeBrief(episode_id=world.episode_id))

    assert [voice["character_id"] for voice in adjusted] == [taro]
    # 二度目は変わる欄が無いので書かない
    assert again == []
    assert "よう" in prompts[0]
    with get_env_session() as s:
        rows = [row for row in s.get_one(Character, taro).parameters if row.start == Stamp.parse("1200/04/01 12:00:00")]
    # 調整し直しても、行は増えない。変わった欄だけを書き、ほかは前の行のまま
    assert [(row.first_person, row.tone, row.second_person) for row in rows] == [("俺", "砕けた短い言い切り", None)]
    member = next(member for member in first["この話"]["登場人物"] if member["人物id"] == taro)
    assert (member["一人称"], member["口調"], member["二人称"]) == ("俺", "砕けた短い言い切り", "あなた")
    assert "直前の話の本文(古い順)" in prompts[0]


def test_refresh_voices_keeps_voices_decided_after_the_samples(shown, world, mock_ai, monkeypatch):
    taro, hanako = world.character_ids
    with get_env_session() as s:
        s.add(Episode(story_id=world.story_id, title="前の話", plot_text="前", main_text="「よう」と太郎が笑った。",
                      start="1200/03/01 12:00:00"))
        # 見本の話より後に、作者が太郎の口調を変えた
        s.add(CharacterParameter(character_id=taro, start=Stamp.parse("1200/03/15 12:00:00"), tone="作者が決めた口調"))
        s.commit()
    asked = []

    def generate(prompt, output, *args, **kwargs):
        if output is VoiceDrafts:
            asked.append(prompt)
            return VoiceDrafts(voices=[
                VoiceDraft(character_id=taro, first_person=None, second_person=None, third_person=None,
                           tone="見本に戻した口調", dialect=None)])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    shown(RefreshVoices(episode_id=world.episode_id))
    result = shown(ReadEpisodeBrief(episode_id=world.episode_id))

    # 変える前の見本では太郎の話し方を直さない。AI が太郎を返しても書かない
    assert all("テスト太郎" not in prompt for prompt in asked)
    member = next(member for member in result["この話"]["登場人物"] if member["人物id"] == taro)
    assert member["口調"] == "作者が決めた口調"


TARO, HANAKO, STRANGER = 1, 2, 3


def _staged() -> SessionStore:
    """太郎と花子が知り合いで、二人と初対面の人がいる話の手番のファイル。"""
    session = SessionStore(1)
    session.set_stage({TARO: "テスト太郎", HANAKO: "テスト花子", STRANGER: "見知らぬ人"}, [(HANAKO, TARO)])
    return session


def _ids(records: list[store.Record]) -> list[int]:
    return [record.id for record in records]


def test_stage_copies_the_cast_and_the_acquaintances(shown, world, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    taro, hanako = world.character_ids
    session = SessionStore(world.episode_id)
    # 登場人物を写すまでは、手番を足せない
    with pytest.raises(ValueError, match="stage"):
        session.add({"witness_ids": [], "turns": [{"character_id": taro, "request": "一手"}]})

    episode_session.stage(session)

    state = session.load()
    assert state.cast == {taro: "テスト太郎", hanako: "テスト花子"}
    assert state.acquaintances == [sorted([taro, hanako])]


def test_session_turns():
    session = _staged()
    taro_turn, hanako_turn = _ids(session.add({"witness_ids": [], "turns": [
        {"character_id": TARO, "time": "1200/04/01 12:00", "request": "市で花子を見かけた"},
        {"character_id": HANAKO, "request": "太郎が手を振った"}]}))

    assert session.turn(HANAKO)["status"] == "waiting"
    # 人物役には番の行の時刻を渡さない
    assert session.turn(TARO)["record"] == {"id": taro_turn, "seen": [], "request": "市で花子を見かけた"}
    with pytest.raises(ValueError, match="まだ番が来ていない"):
        session.answer(hanako_turn, {"action": "手を振り返す"})

    session.answer(taro_turn, {"thought": "久しぶりだ", "action": "手を振る", "speech": "よう"})
    assert session.turn(HANAKO)["status"] == "turn"
    with pytest.raises(ValueError, match="action が空"):
        session.answer(hanako_turn, {"speech": "おう"})
    session.answer(hanako_turn, {"action": "手を振り返す"})
    with pytest.raises(ValueError, match="もう行動が入っている"):
        session.answer(hanako_turn, {"action": "もう一度"})

    assert session.turn(TARO)["status"] == "waiting"
    records = session.load().records
    assert [(record.character_id, record.kind) for record in records] == [(TARO, "人物"), (HANAKO, "人物")]
    assert (records[0].speech, records[0].time) == ("よう", "1200/04/01 12:00")
    assert session.actor_time(TARO) == "1200/04/01 12:00"
    assert session.actor_time(HANAKO) is None


def test_answers_are_written_one_file_per_record():
    session = _staged()
    [turn] = session.add({"witness_ids": [], "turns": [{"character_id": TARO, "request": "一手"}]})
    session.answer(turn.id, {"action": "見上げる", "aim": "空を見る"})

    # 行のファイルは語り部だけが書き、一手は行ごとのファイルに入る(同時に動く人物役が書き合わない)
    rows = json.loads((session.dir / "session.json").read_text(encoding="utf-8"))["records"]
    assert rows[0]["action"] is None
    assert json.loads((session.dir / "answers" / f"{turn.id}.json").read_text(encoding="utf-8")) == {
        "thought": None, "action": "見上げる", "speech": None, "aim": "空を見る"}
    assert session.load().records[0].action == "見上げる"


def test_narration_and_moves_reach_the_witnesses_once():
    session = _staged()
    narration, taro_turn = _ids(session.add({"narration": "市に鐘が鳴った", "witness_ids": [TARO, HANAKO], "turns": [
        {"character_id": TARO, "time": "1200/04/01 12:00", "request": "鐘を聞いての一手"}]}))

    # 語りの行は手番に数えず、見聞きする人物の番に届く
    assert session.turn(TARO)["record"] == {"id": taro_turn, "seen": ["市に鐘が鳴った"], "request": "鐘を聞いての一手"}
    session.answer(taro_turn, {"thought": "花子だ", "action": "手を振る", "speech": "よう", "aim": "気づかせる"})
    [hanako_turn] = _ids(session.add({"witness_ids": [TARO], "turns": [{"character_id": HANAKO, "request": "返事"}]}))
    # ほかの人物の一手は行動とセリフだけが名前付きで届き、内心・狙いは届かない
    assert session.turn(HANAKO)["record"]["seen"] == ["市に鐘が鳴った", "テスト太郎: 手を振る「よう」"]
    session.answer(hanako_turn, {"action": "笑う"})
    [taro_next] = _ids(session.add({"witness_ids": [], "turns": [{"character_id": TARO, "request": "次の一手"}]}))
    # 前の番で受け取った語りと、自分の一手は届け直さない
    assert session.turn(TARO)["record"]["seen"] == ["テスト花子: 笑う"]

    assert [played["seen"] for played in session.played(TARO)] == [["市に鐘が鳴った"]]
    first = session.load().records[0]
    assert (first.id, first.kind, first.character_id, first.witnesses, first.time) == (
        narration, "語り", None, [TARO, HANAKO], "1200/04/01 12:00")
    with pytest.raises(ValueError, match="人物の行でない"):
        session.answer(narration, {"action": "鳴らす"})
    assert session.clear(taro_next) == 1
    assert session.clear() == 3


def test_add_checks_the_witnesses():
    session = _staged()
    turn = {"character_id": TARO, "request": "一手"}

    with pytest.raises(ValueError, match="知り合いでない"):
        session.add({"witness_ids": [HANAKO, STRANGER], "turns": [turn]})
    with pytest.raises(ValueError, match="登場人物でない"):
        session.add({"witness_ids": [99], "turns": [turn]})
    with pytest.raises(ValueError, match="登場人物でない"):
        session.add({"witness_ids": [], "turns": [{"character_id": 99, "request": "一手"}]})
    with pytest.raises(ValueError, match="witness_ids"):
        session.add({"narration": "鐘が鳴った", "turns": []})
    with pytest.raises(ValueError, match="turns か narration"):
        session.add({"witness_ids": [], "turns": []})
    # 見聞きする人物を渡し忘れた手番は、一手が誰にも届かないまま進むので断る
    with pytest.raises(ValueError, match="見聞きする人物"):
        session.add([turn])
    # 欄の名を書き違えると、黙って空のまま進むので断る
    with pytest.raises(ValueError, match="知らない欄"):
        session.add({"witnesses": [HANAKO], "turns": [turn]})
    assert session.load().records == []
    # 手番の無い語りは、時刻を渡さなければ断り、渡せばその時刻で入る
    with pytest.raises(ValueError, match="語りの時刻"):
        session.add({"narration": "半刻が過ぎた", "witness_ids": [TARO], "turns": []})
    [alone_narration] = session.add({"narration": "半刻が過ぎた", "witness_ids": [TARO], "time": "1200/04/01 12:30",
                                     "turns": []})
    assert alone_narration.time == "1200/04/01 12:30"
    # 誰にも見せない一手は、空を渡せば通る
    [alone] = session.add([{"character_id": TARO, "request": "一人で考える", "witness_ids": []}])
    assert alone.witnesses == []

    # 語りは知り合いでなくても届く。手番ごとの見聞きする人物は、語りの人物に代わる
    added = session.add({"narration": "鐘が鳴った", "witness_ids": [TARO, HANAKO, STRANGER],
                         "turns": [{"character_id": TARO, "request": "一手", "witness_ids": [HANAKO]}]})
    assert [record.witnesses for record in added] == [[TARO, HANAKO, STRANGER], [HANAKO]]


def test_moves_returns_the_moves_without_the_requests():
    session = _staged()
    narration, taro_turn, hanako_turn = _ids(session.add({
        "narration": "市に鐘が鳴った", "witness_ids": [TARO, HANAKO],
        "turns": [{"character_id": TARO, "request": "一手"}, {"character_id": HANAKO, "request": "一手"}]}))

    # 待たずに、埋まっていない行を返す
    assert episode_session.moves(session, narration - 1) == {"answers": [], "pending": [taro_turn, hanako_turn]}
    session.answer(taro_turn, {"thought": "鐘だ", "action": "見上げる"})
    assert episode_session.moves(session, narration - 1) == {
        "answers": [{"id": taro_turn, "character": "テスト太郎", "thought": "鐘だ", "action": "見上げる", "speech": None,
                     "aim": None}],
        "pending": [hanako_turn]}
    assert episode_session.moves(session, taro_turn)["answers"] == []
    # 語り部の読む行は、人物を名前にする
    rows = [episode_session._row(record, session.load().cast) for record in session.load().records]
    assert [(row["kind"], row["character"], row["witnesses"]) for row in rows] == [
        ("語り", None, [TARO, HANAKO]), ("人物", "テスト太郎", [HANAKO]), ("人物", "テスト花子", [TARO])]


def test_clear_lets_the_actors_play_again():
    session = _staged()
    session.add({"witness_ids": [], "turns": [{"character_id": TARO, "request": "市に着いた"}]})
    assert session.turn(HANAKO)["status"] == "waiting"

    assert session.clear() == 1
    assert session.load().records == []
    # 登場人物と知り合いの組は残るので、stage を読み直さずに足せる
    [turn] = session.add({"witness_ids": [], "turns": [{"character_id": HANAKO, "request": "市に着いた"}]})
    # 前の埋まっていない手番が消えたので、新しい手番が回る
    assert session.turn(HANAKO)["status"] == "turn"
    # 消した行の id は使い直さない(止めた人物役が、古い行の id に一手を入れないように)
    assert turn.id == 2


def test_clear_from_a_record_replays_from_there():
    session = _staged()
    first, second, third = _ids(session.add({"witness_ids": [], "turns": [
        {"character_id": TARO, "request": "市に着いた"}, {"character_id": HANAKO, "request": "太郎が来た"},
        {"character_id": TARO, "request": "花子が笑った"}]}))
    session.answer(first, {"thought": "混んでいる", "action": "辺りを見回す", "speech": "さて"})
    session.answer(second, {"action": "笑う"})

    assert session.clear(second) == 2
    assert _ids(session.load().records) == [first]
    assert not (session.dir / "answers" / f"{second}.json").exists()
    # 起こし直した人物役は、残った自分の手番だけを読む(時刻とほかの人物の行は入らない)
    assert session.played(TARO) == [{
        "id": first, "seen": [], "request": "市に着いた", "thought": "混んでいる", "action": "辺りを見回す", "speech": "さて",
        "aim": None}]
    assert session.played(HANAKO) == []
    with pytest.raises(ValueError, match="セッションの行でない"):
        session.clear(third)


def test_read_turn_reads_the_record_the_narrator_sent():
    session = _staged()
    taro_turn, hanako_turn, taro_next = _ids(session.add({"witness_ids": [], "turns": [
        {"character_id": TARO, "request": "市に着いた"}, {"character_id": HANAKO, "request": "太郎が来た"},
        {"character_id": TARO, "request": "花子が笑った"}]}))

    assert episode_session.read_turn(session, TARO, taro_turn)["record"]["request"] == "市に着いた"
    # 前の手番が埋まる前に知らされたら、待たずにまだだと返す
    assert episode_session.read_turn(session, HANAKO, hanako_turn)["status"] == "waiting"
    # 知らされた行より前に、自分の埋まっていない番があれば、その行を返す
    assert episode_session.read_turn(session, TARO, taro_next) == {"status": "other", "record_id": taro_turn}


def test_simultaneous_turns_open_together():
    session = _staged()
    taro_turn, hanako_turn = _ids(session.add({"witness_ids": [TARO, HANAKO], "simultaneous": True, "turns": [
        {"character_id": TARO, "request": "梁を押さえる"}, {"character_id": HANAKO, "request": "男を引き出す"}]}))
    [taro_next] = _ids(session.add({"witness_ids": [HANAKO], "turns": [{"character_id": TARO, "request": "次の一手"}]}))

    # 組の手番は、前の人物の一手を待たずに一度に番が開く。組でない次の手番は、組が埋まるまで待つ
    assert session.turn(HANAKO)["record"]["id"] == hanako_turn
    session.answer(hanako_turn, {"action": "男の脇を抱える"})
    assert session.turn(TARO)["record"]["id"] == taro_turn
    # 同じ組のほかの人物の一手は、同時に動いたので届かない
    assert session.turn(TARO)["record"]["seen"] == []
    session.answer(taro_turn, {"action": "灯りで梁を押さえる"})
    # 組の一手は、次の自分の番で届く
    assert session.turn(TARO)["record"] == {"id": taro_next, "seen": ["テスト花子: 男の脇を抱える"], "request": "次の一手"}
    assert [record.simultaneous for record in session.load().records] == [False, True, False]
    assert session.text() == "梁を押さえる\n灯りで梁を押さえる\n男を引き出す\n男の脇を抱える\n次の一手"


def test_write_file_keeps_the_whole_result(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(episode_session, "OUT_DIR", tmp_path)
    result = {"a": "長" * 50000}
    written = episode_session.write_file(result, "knowledge-e1-c2")
    # 標準出力にはパスだけを出し、中身は全部ファイルにある
    assert written["file"] == str(tmp_path / "knowledge-e1-c2.json")
    assert json.loads((tmp_path / "knowledge-e1-c2.json").read_text(encoding="utf-8")) == result


def _main_text(world) -> str:
    with get_env_session() as s:
        return s.get_one(Episode, world.episode_id).main_text


def test_narrator_appends_to_the_main_text(shown, world):
    shown(AppendText(episode_id=world.episode_id, text="太郎は振り向いた。\n「よう」"))

    assert _main_text(world) == "市で二人が出会った。\n太郎は振り向いた。\n「よう」"
    with pytest.raises(ValueError, match="text が空"):
        AppendText(episode_id=world.episode_id, text=" ").run()


def test_narrator_rewrites_what_the_author_noted_like_a_plot(shown, world):
    shown(AppendText(episode_id=world.episode_id, text="太郎が花子に声をかける。\n花子は驚く。"))
    # 作者の箇条を本文の文に起こし直す
    shown(ReplaceText(episode_id=world.episode_id, old="太郎が花子に声をかける。\n花子は驚く。",
                      new="「よう」\n太郎の声に、花子の肩が跳ねた。"))
    assert _main_text(world) == "市で二人が出会った。\n「よう」\n太郎の声に、花子の肩が跳ねた。"
    with pytest.raises(ValueError, match="0 度"):
        ReplaceText(episode_id=world.episode_id, old="鐘が鳴った。", new="鐘").run()


def test_wait_returns_without_the_moves():
    session = _staged()
    taro_turn, hanako_turn = _ids(session.add({
        "witness_ids": [TARO, HANAKO], "simultaneous": True,
        "turns": [{"character_id": TARO, "request": "一手"}, {"character_id": HANAKO, "request": "一手"}]}))

    # 待ちきれなければ、まだ埋まっていない行を返す
    assert episode_session.wait(session, [taro_turn, hanako_turn], 0) == {"filled": [], "pending": [taro_turn, hanako_turn]}
    session.answer(taro_turn, {"action": "見上げる"})
    session.answer(hanako_turn, {"action": "うなずく"})
    # 一手は人物役の返りで読むので、埋まった行の id だけを返す
    assert episode_session.wait(session, [taro_turn, hanako_turn], 0) == {"filled": [taro_turn, hanako_turn]}
    with pytest.raises(ValueError, match="無い行"):
        episode_session.wait(session, [hanako_turn + 1], 0)


def _off_stage_acquaintance(shown, world) -> int:
    """太郎・花子と関係はあるが、話に出ない人物。"""
    taro, hanako = world.character_ids
    other = shown(CommitCharacter(CharacterCreateForm(name="テスト次郎", text="次郎の芯", plot="次郎の先", start="1170/01/01")))
    for character_id in (taro, hanako):
        shown(CommitCharacterRelation(CharacterRelationCreateForm(
            character_1_id=character_id, character_2_id=other["id"], relation="遠い親戚", start="1180/01/01")))
    return other["id"]


def test_read_knowledge_tells_only_the_people_in_the_scene(shown, world):
    _off_stage_acquaintance(shown, world)

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=world.character_ids[0]))

    # 話に出ない人物は、関係の名前と間柄だけ。外見・芯・来歴は渡さない
    assert [character["名前"] for character in result["知っている人物"]] == ["テスト花子"]
    assert "テスト次郎" in [relation["誰へ"] for relation in result["関係"]]
    # 話を渡さないときは、関係のある人物すべて
    by_time = shown(ReadKnowledge(character_id=world.character_ids[0], time="1200/04/01"))
    assert [character["名前"] for character in by_time["知っている人物"]] == ["テスト花子", "テスト次郎"]


def test_read_episode_brief_recent_histories(shown, world, mock_ai):
    _, hanako = world.character_ids
    shown(UpdateCharacter(CharacterUpdateForm(id=hanako, histories=[
        CharacterHistoryRow(start=1180, kind="持ち物", description="母の形見の指輪"),
        *(CharacterHistoryRow(start=1190 + year, description=f"出来事{year}") for year in range(7))])))
    _dress(shown, hanako)

    result = shown(ReadEpisodeBrief(episode_id=world.episode_id))

    hanako_row = next(member for member in result["この話"]["登場人物"] if member["人物id"] == hanako)
    # 出来事の行は新しいほうから決まった数だけ、種別の付いた行は古くても効いていれば渡す
    limit = constants.EPISODE_BRIEF_HISTORY_LIMIT
    assert [row["来歴"] for row in hanako_row["来歴(古い順)"]] == [
        "母の形見の指輪", *(f"出来事{year}" for year in range(7 - limit, 7))]
    # 装いは身に着けている物ごとの今の姿で渡し、スキルには入れない
    assert hanako_row["装い"] == ["腰に木剣", "灰色の外套"]
    assert hanako_row["スキル"] == []


def test_read_episode_brief_ideas_by_name_only(shown, world, mock_ai, monkeypatch):
    other = shown(CommitIdea(IdeaCreateForm(name="都の灯台", kind="施設", text="テスト術で灯す台", histories=[
        IdeaHistoryRow(location_id=world.location_id, start="1150/01/01", name="都の灯台")])))

    def generate(prompt, output, *args, **kwargs):
        if output is IdeaDraftsByAI:
            return output(ideas=[IdeaDraftByAI(keyword="テスト術", variants=[], description="灯をともす術", coined=True,
                                               kind="技術", start=None, end=None)])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    ideas = {idea["アイデアid"] for idea in shown(ReadEpisodeBrief(episode_id=world.episode_id))["この話"]["設定"]}

    # 語が説明の文にだけ出るアイデアは、語の指す事柄と別物のことが多いので渡さない
    assert world.idea_id in ideas
    assert other["id"] not in ideas


def test_read_episode_casting_without_episodes(shown, world, mock_ai, monkeypatch):
    other = _off_stage_acquaintance(shown, world)
    asked = []
    monkeypatch.setattr(ai_client, "generate", lambda *args, **kwargs: asked.append(args))

    result = shown(ReadEpisodeCasting(episode_id=world.episode_id))

    # AI を呼ばず、関わった話は人物ごとの入口で読む。語り部には筋書きも来歴も渡さない
    assert asked == []
    taro_row = next(member for member in result["登場人物"] if member["人物id"] == world.character_ids[0])
    assert not {"関わった話(古い順)", "筋書き", "来歴(古い順)"} & set(taro_row)
    # 候補は結ぶかを決める名前と人物像だけ
    candidate = next(member for member in result["登場人物の候補"] if member["人物id"] == other)
    assert candidate == {"人物id": other, "名前": "テスト次郎", "種別": "人物", "年齢": 30, "人物像": "次郎の芯"}


def test_read_character_episodes_only_recent_texts(shown, world, monkeypatch):
    taro, _ = world.character_ids
    monkeypatch.setattr(constants, "EPISODE_RECENT_APPEARANCE_COUNT", 2)
    with get_env_session() as s:
        for month in ["01", "02", "03"]:
            episode = Episode(story_id=world.story_id, title=f"{month}月の話", plot_text=f"{month}月のプロット",
                              main_text=f"{month}月の本文。", start=f"1200/{month}/01 12:00:00")
            s.add(episode)
            s.flush()
            s.add(EpisodeCharacter(episode_id=episode.id, character_id=taro))
        s.commit()

    result = shown(ReadCharacterEpisodes(episode_id=world.episode_id, character_id=taro))

    # 直近の話から数えて、古い順。本文を返し、プロットは返さない
    assert [(row["題"], row["本文"]) for row in result] == [("02月の話", "02月の本文。"), ("03月の話", "03月の本文。")]
    assert "プロット" not in str(result)


def test_read_episode_brief_without_lower_ideas_and_summaries(shown, world, mock_ai, monkeypatch):
    asked = []

    def generate(prompt, output, *args, **kwargs):
        asked.append(output)
        if output is IdeaDraftsByAI:
            return output(ideas=[IdeaDraftByAI(keyword="テスト魔導", variants=["テスト術"], description="都の技術",
                                               coined=False, kind="技術", start=None, end=None)])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    result = shown(ReadEpisodeBrief(episode_id=world.episode_id))

    # 当たった設定に下位(テスト魔導炉)は付けない
    idea_ids = [idea["アイデアid"] for idea in result["この話"]["設定"]]
    assert world.idea_id in idea_ids and world.child_idea_id not in idea_ids
    # 前の話の概要は渡さない(語を挙げるのにだけ AI を呼ぶ)
    assert set(asked) == {IdeaDraftsByAI}
    assert "前の話の概要(古い順)" not in result
