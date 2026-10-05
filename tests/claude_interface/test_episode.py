"""claude が CLI から `show()` で呼ぶ、話(`data_access_logic/episode/`)の入口。"""
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode.read_episodes import ReadEpisodes
from data_access_logic.episode.rewrite_episode_summary import RewriteEpisodeSummary
from data_access_logic.episode.set_episode_synced import SetEpisodeSynced
from data_access_logic.episode.relations import EpisodeRelationsDraft, RelationDraft
from data_access_logic.flows.commit import commit_episode
from db.schema import CharacterRelation, Episode, get_env_session, summary_source_hash
from tool.test.mock_ai_client import MockAIClient


class _RelatingAI(MockAIClient):
    """関係だけは決めた下書きを返し、ほかの段はモックのまま。"""

    def __init__(self, relations: list[RelationDraft]):
        super().__init__(seed=0)
        self.relations = relations

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort=""):
        if output is EpisodeRelationsDraft:
            self.calls.append({"prompt": prompt, "system": system})
            return EpisodeRelationsDraft(relations=self.relations)
        return super().generate(prompt, output, system, timeout, tools, model, effort)


def test_commit_episode(shown, world, mock_ai):
    result = shown(CommitEpisode(EpisodeCommitForm(
        story_id=world.story_id, title="テスト第二話", plot_text="取引の夜", main_text="夜になった。\n取引がまとまった。",
        start="1200/04/01 15:00:00", end="1200/04/01 20:00:00", viewpoint_character_id=world.character_ids[1],
        location_id=world.location_id, event_seeded=True, synced=True, character_ids=world.character_ids)))

    assert result["story_id"] == world.story_id
    assert (result["title"], result["plot_text"]) == ("テスト第二話", "取引の夜")
    assert "取引がまとまった。" in result["main_text"]
    assert result["letters"] == len(result["main_text"])
    assert (result["start"], result["end"]) == ("1200/04/01 15:00:00", "1200/04/01 20:00:00")
    assert result["viewpoint_character_id"] == world.character_ids[1]
    assert result["location_id"] == world.location_id
    assert (result["event_seeded"], result["synced"]) == (True, True)
    assert result["character_ids"] == world.character_ids
    # 確定のあとに要約・ミームを AI に作らせる。要約は話の行に持つ
    assert mock_ai.calls
    with get_env_session() as s:
        episode = s.get_one(Episode, result["id"])
        assert episode.summary_text
        assert episode.summary_source_hash == summary_source_hash(episode.main_text.strip())


def test_read_episodes(shown, world):
    result = shown(ReadEpisodes(story_id=world.story_id, count=5, before="1200/12/31", text=True))

    assert [episode["id"] for episode in result] == [world.episode_id]
    assert result[0]["main_text"] == "市で二人が出会った。"


def test_set_episode_synced(shown, world):
    result = shown(SetEpisodeSynced(episode_id=world.episode_id, synced=False))

    assert result["id"] == world.episode_id
    assert result["synced"] is False


def test_rewrite_episode_summary(shown, world, mock_ai):
    result = shown(RewriteEpisodeSummary(episode_ids=[world.episode_id]))

    assert [row["id"] for row in result] == [world.episode_id]
    assert result[0]["summary_text"]
    with get_env_session() as s:
        episode = s.get_one(Episode, world.episode_id)
        assert episode.summary_text == result[0]["summary_text"]
        assert episode.summary_source_hash == summary_source_hash(episode.main_text.strip())


def test_commit_episode_relates_the_cast(world):
    taro, hanako = world.character_ids
    stranger = RelationDraft(character_1_id=taro, character_2_id=0, relation="話に出ない人", text="", history="")
    ai = _RelatingAI([
        # 太郎から花子へはすでに「幼なじみ」がいるので足さない
        RelationDraft(character_1_id=taro, character_2_id=hanako, relation="重ねた関係", text="", history=""),
        RelationDraft(character_1_id=hanako, character_2_id=taro, relation="市で出会った人", text="同じ市で商う",
                      history="市で名乗り合った"),
        RelationDraft(character_1_id=hanako, character_2_id=taro, relation="同じ向きの二つ目", text="", history=""),
        stranger])

    result = commit_episode(EpisodeCommitForm(id=world.episode_id, main_text="市で花子が太郎に名乗った。"), ai)

    # 登場人物どうしで、まだ関係の無い向きだけを、話の時刻から足す
    assert [(relation.character_1_id, relation.character_2_id, relation.relation) for relation in result.relations] == [(hanako, taro, "市で出会った人")]
    with get_env_session() as s:
        added = s.get_one(CharacterRelation, result.relations[0].id)
        assert (str(added.start), added.text) == ("1200/04/01 12:00:00", "同じ市で商う")
        assert [(history.start, history.description) for history in added.histories] == [(1200, "市で名乗り合った")]
    assert '"誰から(人物id)"' in ai.calls[-1]["prompt"]
