
import pytest

from ai.claude_code import ai_client
from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story.commit_episode import CommitEpisode
from ai.claude_code.interface.story.commit_story import CommitStory
from db.schema import Character, Episode, EpisodeSummary, Location


@pytest.fixture
def place(session):
    location = Location(name="ノウル", kind="星", text="")
    session.add(location)
    session.commit()
    return location.id


def test_commit_story_returns_row(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place,
                         "narration": "三人称", "state": "構想中",
                         "start": "11572/03/24 00:00:00", "text": "本編"}).run()
    assert story["name"] == "遥かなる幻想郷まで"
    assert story["place_id"] == place
    assert str(story["start"]) == "11572/03/24 00:00:00"


def test_commit_episode_summarizes_the_episode_right_away(session, place, monkeypatch):
    monkeypatch.setattr(ai_client, "try_generate_json",
                        lambda *a, **k: {"summary": "娘が生まれた", "style": "淡々とした語り"})
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    episode = CommitEpisode({"story_id": story["id"], "title": "白い灯り", "text": "骨組み"}).run()

    row = session.query(EpisodeSummary).filter_by(episode_id=episode["id"]).one()
    assert (row.summary, row.style) == ("娘が生まれた", "淡々とした語り")


def test_commit_story_requires_name(place):
    with pytest.raises(ValueError):
        CommitStory({"place_id": place}).run()


def test_commit_story_rejects_unknown_place():
    with pytest.raises(UnknownRecordError):
        CommitStory({"name": "作品", "place_id": 9999}).run()


def test_commit_episode_updates_by_id(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    first = CommitEpisode({"story_id": story["id"], "title": "白い灯り", "key": "種"}).run()

    updated = CommitEpisode({"id": first["id"], "text": "本文"}).run()

    assert updated["id"] == first["id"]
    assert (updated["key"], updated["text"], updated["letters"]) == ("種", "本文", 2)


def test_commit_episode_lays_out_the_text(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    episode = CommitEpisode({"story_id": story["id"], "title": "白い灯り",
                             "text": "扉が開いた。ミレアが来た。\n◇\n三日後。"}).run()

    assert episode["text"] == "扉が開いた。\nミレアが来た。\n\n\n三日後。"
    assert episode["letters"] == len(episode["text"])


def test_commit_episode_rejects_unknown_id(place):
    with pytest.raises(UnknownRecordError):
        CommitEpisode({"id": 9999, "text": "本文"}).run()


def test_commit_episode_requires_story_id_for_new_episode(place):
    with pytest.raises(ValueError):
        CommitEpisode({"title": "白い灯り", "text": "本文"}).run()


def test_commit_episode_accepts_key_only(session, place):
    kashiru = Character(name="カシル", text="")
    ministry = Location(name="エンピレオ 血統管理省", kind="施設", text="")
    session.add_all([kashiru, ministry])
    session.commit()
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    episode = CommitEpisode({"story_id": story["id"], "title": "白い灯り",
                             "key": "人工母体から娘が生まれる", "start": "11572/03/25 00:00:00",
                             "viewpoint_character_id": kashiru.id, "place_id": ministry.id}).run()
    assert episode["key"] == "人工母体から娘が生まれる"
    assert (episode["text"], episode["letters"]) == ("", 0)
    assert (episode["viewpoint_character_id"], episode["place_id"]) == (kashiru.id, ministry.id)
    assert str(episode["start"]) == "11572/03/25 00:00:00"


def test_commit_episode_requires_key_or_text(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    with pytest.raises(ValueError):
        CommitEpisode({"story_id": story["id"], "title": "白い灯り"}).run()


def test_commit_episode_writes_characters(session, place):
    first = Character(name="甲", text="")
    second = Character(name="乙", text="")
    session.add_all([first, second])
    session.commit()
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    episode = CommitEpisode({"story_id": story["id"], "title": "白い灯り", "key": "種",
                             "character_ids": [first.id, second.id]}).run()
    assert episode["character_ids"] == [first.id, second.id]

    # character_ids を渡さない直しは、既存の登場人物を変えない
    unchanged = CommitEpisode({"id": episode["id"], "title": "白い灯り(改)"}).run()
    assert unchanged["character_ids"] == [first.id, second.id]

    # character_ids を渡して直せば全置換、空リストなら全削除
    replaced = CommitEpisode({"id": episode["id"], "character_ids": [second.id]}).run()
    assert replaced["character_ids"] == [second.id]
    cleared = CommitEpisode({"id": episode["id"], "character_ids": []}).run()
    assert cleared["character_ids"] == []
