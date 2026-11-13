"""claude が CLI から `show()` で呼ぶ、話(`data_access_logic/episode/`)の入口。"""
from sqlalchemy import select

from data_access_logic.episode.apply_outcomes import ApplyOutcomes
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeReviseForm
from data_access_logic.episode.outcomes import CharacterOutcome, MetCharacter, OutcomesDraft, SessionSpeech, WornItem
from data_access_logic.episode.read_episodes import ReadEpisodes
from data_access_logic.episode.reflect_episode import ReflectEpisode
from data_access_logic.episode.revise_episode import ReviseEpisode
from db.schema import (
    CharacterHistory, CharacterLocation, CharacterRelation, CharacterSkill, CharacterSkillHistory, CharacterSpeech,
    Episode, StyleScope, get_env_session, summary_source_hash,
)
from tool.test.mock_ai_client import MockAIClient


class _ReflectingAI(MockAIClient):
    """差分だけは決めた下書きを返し、ほかの段はモックのまま。"""

    def __init__(self, outcomes: list[CharacterOutcome]):
        super().__init__(seed=0)
        self.outcomes = outcomes

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="",
                 style_scope: StyleScope | None = StyleScope.ALL):
        if output is OutcomesDraft:
            self.calls.append({"prompt": prompt, "system": system})
            return OutcomesDraft(outcomes=self.outcomes)
        return super().generate(prompt, output, system, timeout, tools, model, effort, style_scope)


def test_commit_episode(shown, world, mock_ai):
    memo = "夜に港で取引がまとまる"
    result = shown(CommitEpisode(EpisodeCommitForm(
        story_id=world.story_id, title="テスト第二話", plot_text=memo, main_text="夜になった。\n取引がまとまった。",
        start="1200/04/01 15:00:00", end="1200/04/01 20:00:00", viewpoint_character_id=world.character_ids[1],
        location_id=world.location_id, character_ids=world.character_ids)))

    assert result["story_id"] == world.story_id
    assert (result["title"], result["plot_text"]) == ("テスト第二話", memo)
    assert "取引がまとまった。" in result["main_text"]
    assert result["letters"] == len(result["main_text"])
    assert (result["start"], result["end"]) == ("1200/04/01 15:00:00", "1200/04/01 20:00:00")
    assert result["viewpoint_character_id"] == world.character_ids[1]
    assert result["location_id"] == world.location_id
    assert result["character_ids"] == world.character_ids
    # 確定のあとに AI を回さない(世界への反映は `ApplyOutcomes` / `ReflectEpisode`)
    assert not mock_ai.calls


def test_read_episodes(shown, world):
    result = shown(ReadEpisodes(story_id=world.story_id, count=5, before="1200/12/31", text=True))

    assert [episode["id"] for episode in result] == [world.episode_id]
    assert result[0]["main_text"] == "市で二人が出会った。"


def test_apply_outcomes_without_ai(shown, world, mock_ai):
    taro, hanako = world.character_ids
    time = "1200/04/01 12:00:00"
    with get_env_session() as s:
        coat = CharacterSkill(character_id=hanako, name="灰色の外套", kind="装い", text="灰色の外套",
                              histories=[CharacterSkillHistory(start="1199/01/01", description="灰色の外套を羽織っている")])
        s.add(coat)
        s.commit()
        coat_id = coat.id
        hanako_histories = s.query(CharacterHistory).filter_by(character_id=hanako).count()

    result = shown(ApplyOutcomes(episode_id=world.episode_id, outcomes=[
        CharacterOutcome(character_id=taro, histories=["花子が借金を隠していると知った"],
                         # 太郎から花子へはすでに「幼なじみ」があるので足さない
                         met=[MetCharacter(character_id=hanako, relation="重ねた関係", history="市で会った")],
                         worn=[WornItem(name="短剣", description="市で短剣を買って腰に差した")], moved_to="テスト村"),
        CharacterOutcome(character_id=hanako,
                         met=[MetCharacter(character_id=taro, relation="市で出会った人", history="市で名乗り合った")],
                         removed=["灰色の外套", "持っていない物"]),
        CharacterOutcome(character_id=0, histories=["話に出ない人の行"]),
    ], speeches=[SessionSpeech(character_id=taro, text="やあ"), SessionSpeech(character_id=hanako, text="どうも"),
                 SessionSpeech(character_id=0, text="話に出ない人のセリフ")]))

    assert not mock_ai.calls
    assert result["histories"] == 1
    assert result["relations"] == ["テスト花子→テスト太郎: 市で出会った人"]
    assert result["worn"] == ["テスト太郎: 短剣"]
    assert result["removed"] == ["テスト花子: 灰色の外套"]
    assert result["moves"] == ["テスト太郎 → テスト村"]
    assert result["speeches"] == 2
    assert len(result["skipped"]) == 2
    with get_env_session() as s:
        # 知ったことは知った本人だけが知る行にし、秘密を持つ人物(花子)の行には触れない
        learned = s.scalars(select(CharacterHistory).where(
            CharacterHistory.character_id == taro, CharacterHistory.description == "花子が借金を隠していると知った")).one()
        assert str(learned.start) == time
        assert [knower.knower_id for knower in learned.knowers] == [taro]
        assert s.query(CharacterHistory).filter_by(character_id=hanako).count() == hanako_histories
        assert [str(history.end) for history in s.get_one(CharacterSkill, coat_id).histories] == [time]
        dagger = s.scalars(select(CharacterSkill).where(CharacterSkill.character_id == taro,
                                                        CharacterSkill.name == "短剣")).one()
        assert dagger.kind == "装い" and [str(history.start) for history in dagger.histories] == [time]
        assert s.scalars(select(CharacterLocation.location_id).where(
            CharacterLocation.character_id == taro, CharacterLocation.start == time)).all() == [world.neighbor_id]
        assert s.query(CharacterRelation).filter_by(character_1_id=taro, character_2_id=hanako).count() == 1
        speeches = s.scalars(select(CharacterSpeech).where(CharacterSpeech.episode_id == world.episode_id)
                             .order_by(CharacterSpeech.position)).all()
        main_text = s.get_one(Episode, world.episode_id).main_text
        assert [(speech.character_id, speech.verbatim, speech.vague) for speech in speeches] == [
            (taro, "やあ", "やあ"), (hanako, "どうも", "どうも")]
        assert {speech.source_hash for speech in speeches} == {summary_source_hash(main_text)}


def test_reflect_episode_drafts_outcomes_once(shown, world):
    taro, _ = world.character_ids
    ai = _ReflectingAI([CharacterOutcome(character_id=taro, histories=["市で花子と再会した"])])

    result = shown(ReflectEpisode(episode_id=world.episode_id, ai=ai))

    assert result["histories"] == 1
    reflect_calls = [call for call in ai.calls if "今の装い" in call["prompt"]]
    assert len(reflect_calls) == 1 and "市で二人が出会った。" in reflect_calls[0]["prompt"]
    # 本文からセリフを拾わない(AI は差分の一度だけ)
    assert result["speeches"] == 0
    assert len(ai.calls) == 1


def test_revise_episode(shown, world, mock_ai):
    result = shown(ReviseEpisode(EpisodeReviseForm(id=world.episode_id, main_text="市で二人が出会い、名乗り合った。")))

    assert "名乗り合った。" in result["main_text"]
    # 渡さなかったプロット・題は空で上書きしない
    assert result["plot_text"] and result["title"]


def test_revise_episode_runs_no_ai(world, mock_ai):
    with get_env_session() as s:
        before = s.query(CharacterRelation).count()

    plot = "市で出会う\n\n## 推敲\n- 名乗りを足す"
    ReviseEpisode(EpisodeReviseForm(id=world.episode_id, main_text="市で花子が太郎に名乗った。", plot_text=plot)).run()

    # 本文から関係・居場所を動かさず、ミーム・種も抜き出さない
    assert not mock_ai.calls
    with get_env_session() as s:
        assert s.query(CharacterRelation).count() == before
        assert s.get_one(Episode, world.episode_id).plot_text == plot
