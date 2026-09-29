"""claude が CLI から `show()` で呼ぶ、話(`data_access_logic/episode/`)の入口。"""
from ai.claude_code import ai_client
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeForm
from data_access_logic.episode.generate_episode import GenerateEpisode
from data_access_logic.episode.generate_frame import GenerateFrame
from data_access_logic.episode.complete_key import CompleteKey
from data_access_logic.episode.models import (
    EpisodeCastingDraft, EpisodeCharacterCandidateDraft, EpisodeLocationCandidateDraft,
)
from data_access_logic.episode.list_unsynced_episodes import ListUnsyncedEpisodes
from data_access_logic.episode.read_episodes import ReadEpisodes
from data_access_logic.episode.revise_episode import ReviseEpisode
from data_access_logic.episode.set_episode_synced import SetEpisodeSynced
from db.schema import Character, ConfirmStatus, Location, get_env_session


def test_commit_episode(shown, world, mock_ai):
    result = shown(CommitEpisode(EpisodeCommitForm(
        story_id=world.story_id, title="テスト第二話", key="取引の夜", text="夜になった。\n取引がまとまった。",
        start="1200/04/01 15:00:00", end="1200/04/01 20:00:00", viewpoint_character_id=world.character_ids[1],
        location_id=world.location_id, event_seeded=True, synced=True, character_ids=world.character_ids)))

    assert result["story_id"] == world.story_id
    assert (result["title"], result["key"]) == ("テスト第二話", "取引の夜")
    assert "取引がまとまった。" in result["text"]
    assert result["letters"] == len(result["text"])
    assert (result["start"], result["end"]) == ("1200/04/01 15:00:00", "1200/04/01 20:00:00")
    assert result["viewpoint_character_id"] == world.character_ids[1]
    assert result["location_id"] == world.location_id
    assert (result["event_seeded"], result["synced"]) == (True, True)
    assert result["character_ids"] == world.character_ids
    # 確定のあとに要約・ミームを AI に作らせる
    assert mock_ai.calls


def test_generate_episode(shown, world, mock_ai):
    result = shown(GenerateEpisode(
        episode=EpisodeForm(
            story_id=world.story_id, title="生成の話", key="市の翌朝", start="1200/04/02 08:00:00",
            end="1200/04/02 12:00:00", viewpoint_character_id=world.character_ids[0], location_id=world.location_id,
            character_ids=world.character_ids),
        model="claude-haiku-4-5", effort="low",
        shared_style_extra="共有の文体の好み", style_extra="話の文体の好み"))

    assert result["story_id"] == world.story_id
    assert result["key"] == "市の翌朝"
    assert result["start"] == "1200/04/02 08:00:00"
    assert result["viewpoint_character_id"] == world.character_ids[0]
    assert result["location_id"] == world.location_id
    assert result["character_ids"] == world.character_ids
    assert result["text"]
    assert any(call["prompt"] and "話の文体の好み" in (call["system"] or "") + call["prompt"] for call in mock_ai.calls)


def test_generate_frame(shown, world, mock_ai):
    result = shown(GenerateFrame(
        frame=EpisodeForm(
            story_id=world.story_id, title="枠の話", key="市のあと", start="1200/04/03", end="1200/04/04",
            viewpoint_character_id=world.character_ids[1], location_id=world.neighbor_id,
            character_ids=[world.character_ids[1]]),
        character_ids=world.character_ids))

    assert result["story_id"] == world.story_id
    assert result["viewpoint_character_id"] == world.character_ids[1]
    assert result["location_id"] == world.neighbor_id
    assert result["character_ids"] == world.character_ids
    assert result["text"] == ""
    assert mock_ai.calls


def test_complete_key(shown, world, mock_ai):
    result = shown(CompleteKey(
        episode=EpisodeForm(
            story_id=world.story_id, key="宿での夜", start="1200/04/02 20:00:00", location_id=world.location_id,
            character_ids=[world.character_ids[0]]),
        order="雨の音を効かせて静かに"))

    # 元の種は補完したあらすじで置き換える
    assert result["key"] and "宿での夜" not in result["key"]
    assert any('"作者の注文": "雨の音を効かせて静かに"' in call["prompt"] for call in mock_ai.calls)
    assert result["location_id"] == world.location_id
    assert result["character_ids"] == [world.character_ids[0]]
    assert result["text"] == ""


def test_complete_key_adds_missing(shown, world, mock_ai, monkeypatch):
    # モックは null を取れる欄に null を返すので、足りない人物・舞台の候補だけは決まった値を返させる
    def generate(prompt, output, system=None, timeout=120.0, model="", effort=""):
        if output is EpisodeCastingDraft:
            return EpisodeCastingDraft(
                characters=[EpisodeCharacterCandidateDraft(called="宿の女将", text="市の外れの宿を切り盛りする")],
                location=EpisodeLocationCandidateDraft(name="ミナト亭", kind="宿", text="市の外れの宿", environment=""))
        return mock_ai.generate(prompt, output, system, timeout, model=model, effort=effort)
    monkeypatch.setattr(ai_client, "generate", generate)

    result = shown(CompleteKey(
        episode=EpisodeForm(
            story_id=world.story_id, key="宿での夜", start="1200/04/02 20:00:00", location_id=world.location_id,
            character_ids=[world.character_ids[0]])))

    assert result["character_ids"][0] == world.character_ids[0]
    assert len(result["character_ids"]) == 2
    with get_env_session() as s:
        added = s.get_one(Character, result["character_ids"][1])
        assert added.confirmed == ConfirmStatus.APPROVED
        location = s.get_one(Location, result["location_id"])
        assert (location.name, location.parent_id) == ("ミナト亭", world.location_id)


def test_list_unsynced_episodes(shown, world):
    SetEpisodeSynced(episode_id=world.episode_id, synced=False).run()

    result = shown(ListUnsyncedEpisodes(story_id=world.story_id))

    assert [episode["id"] for episode in result] == [world.episode_id]
    assert result[0]["story_name"] == "テスト作品"


def test_read_episodes(shown, world):
    result = shown(ReadEpisodes(story_id=world.story_id, count=5, before="1200/12/31", text=True))

    assert [episode["id"] for episode in result] == [world.episode_id]
    assert result[0]["text"] == "市で二人が出会った。"


def test_revise_episode(shown, world, mock_ai):
    result = shown(ReviseEpisode(
        episode=EpisodeForm(id=world.episode_id, title="推敲した第一話", key="市で出会う(推敲)",
                            viewpoint_character_id=world.character_ids[1]),
        instruction="初登場の人物の外見を厚く書く", character_ids=world.character_ids,
        model="claude-haiku-4-5", effort="low", shared_style_extra="共有の文体の好み", style_extra="話の文体の好み"))

    assert result["id"] == world.episode_id
    # 題は書き直した本文の見出しから読み直し、指示は種の末尾に積む
    assert result["key"] == "市で出会う(推敲)\n\n## 推敲\n\n- 初登場の人物の外見を厚く書く\n"
    assert result["viewpoint_character_id"] == world.character_ids[1]
    assert result["character_ids"] == world.character_ids
    assert any("初登場の人物の外見を厚く書く" in call["prompt"] for call in mock_ai.calls)


def test_set_episode_synced(shown, world):
    result = shown(SetEpisodeSynced(episode_id=world.episode_id, synced=False))

    assert result["id"] == world.episode_id
    assert result["synced"] is False
