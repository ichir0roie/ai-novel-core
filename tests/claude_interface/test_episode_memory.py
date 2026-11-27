"""人物役が前の話を「居合わせた話」の要約で覚える(話の差分の来歴に、話の中でしたことの流れを積まない)。"""
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.episode.summarize_episodes import SummarizeEpisodes
from db.schema import Episode, EpisodeCharacter, EpisodeSummary, get_env_session
from tool.test.mock_ai_client import MockAIClient


def _past_episode(world, start: str, title: str, main_text: str = "港で二人が別れた。") -> int:
    taro = world.character_ids[0]
    with get_env_session() as s, s.begin():
        episode = Episode(story_id=world.story_id, title=title, plot_text="", main_text=main_text, start=start,
                          location_id=world.location_id)
        s.add(episode)
        s.flush()
        s.add(EpisodeCharacter(episode_id=episode.id, character_id=taro))
        return episode.id


def test_knowledge_gives_attended_episodes_with_summaries(shown, world):
    taro = world.character_ids[0]
    old = _past_episode(world, "1199/12/01", "テスト港の別れ")
    _past_episode(world, "1201/01/01", "テスト先の話")
    with get_env_session() as s, s.begin():
        s.add(EpisodeSummary(episode_id=old, source_hash="x", text="港・太郎と花子: 二人は港で別れた。"))

    me = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))["自分"]

    episodes = me["居合わせた話(古い順)"]
    titles = [episode["題"] for episode in episodes]
    # 話の時刻より前の話だけ。演じている話と先の話は入らない
    assert "テスト港の別れ" in titles and "テスト先の話" not in titles and "テスト第一話" not in titles
    assert next(episode for episode in episodes if episode["題"] == "テスト港の別れ")["要約"] == "港・太郎と花子: 二人は港で別れた。"


def test_summarize_episodes_writes_the_episode_and_the_casts_past_episodes(world):
    old = _past_episode(world, "1199/11/01", "テスト要約の無い話", main_text="丘で花を摘んだ。")

    written = SummarizeEpisodes(episode_id=world.episode_id, ai=MockAIClient(seed=1)).result().episodes_summarized

    assert written >= 2
    with get_env_session() as s:
        for episode_id in (world.episode_id, old):
            summary = s.query(EpisodeSummary).filter_by(episode_id=episode_id).one()
            assert summary.text
    # 本文が変わらなければ作り直さない
    assert SummarizeEpisodes(episode_id=world.episode_id, ai=MockAIClient(seed=1)).result().episodes_summarized == 0
