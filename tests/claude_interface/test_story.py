"""claude が CLI から `show()` で呼ぶ、作品(`data_access_logic/story/`)の入口。"""
from data_access_logic.story.commit_story import CommitStory
from data_access_logic.story.delete_story import DeleteStory
from data_access_logic.story.form import StoryCreateForm, StoryUpdateForm
from data_access_logic.story.list_stories import ListStories
from data_access_logic.story.read_brief import ReadBrief
from data_access_logic.story.read_cast import ReadCast
from data_access_logic.story.start_story import StartStory
from data_access_logic.story.update_story import UpdateStory


def test_commit_story(shown, world, mock_ai):
    result = shown(CommitStory(StoryCreateForm(
        name="テスト続編", text="続編の構想", world_id=world.planet_id, place_id=world.neighbor_id, narration="一人称",
        state="構想中", start="1210/01/01", end="1220/01/01", event_seeded=True)))

    assert (result["name"], result["text"]) == ("テスト続編", "続編の構想")
    assert (result["world_id"], result["place_id"]) == (world.planet_id, world.neighbor_id)
    assert (result["narration"], result["state"]) == ("一人称", "構想中")
    assert (result["start"], result["end"]) == ("1210/01/01 00:00:00", "1220/01/01 00:00:00")
    assert result["event_seeded"] is True


def test_delete_story(shown, world):
    # 話を持つ作品は消せないので、話の無い作品を足してから消す
    story_id = CommitStory(StoryCreateForm(name="消す作品", text="消す", place_id=world.place_id)).result().id

    result = shown(DeleteStory(story_id=story_id))

    assert result == {"id": story_id, "name": "消す作品", "place_id": world.place_id, "text": "消す"}


def test_list_stories(shown, world):
    result = shown(ListStories())

    assert world.story_id in [story["id"] for story in result]


def test_read_brief(shown, world):
    result = shown(ReadBrief(place_id=world.place_id, time="1200/04/02", reach=30, full=True))

    assert result


def test_read_cast(shown, world):
    result = shown(ReadCast(story_id=world.story_id, time="1200/04/02", count=3, levels=2))

    assert result


def test_start_story(shown, world):
    result = shown(StartStory(story_id=world.story_id, time="1200/04/02", episodes=5, count=3, reach=30, levels=2,
                              skip_sync=True))

    assert result["stopped"] is False
    assert result["time"] == "1200/04/02 23:59:59"
    assert [episode["id"] for episode in result["episodes"]] == [world.episode_id]
    assert result["cast"] is not None
    assert result["brief"] is not None


def test_update_story(shown, world):
    result = shown(UpdateStory(StoryUpdateForm(
        id=world.story_id, name="テスト作品改", text="改めた構想", world_id=world.planet_id, place_id=world.neighbor_id,
        narration="二人称", state="完結", start="1201/01/01", end="1299/01/01", event_seeded=False)))

    assert (result["name"], result["text"]) == ("テスト作品改", "改めた構想")
    assert (result["world_id"], result["place_id"]) == (world.planet_id, world.neighbor_id)
    assert (result["narration"], result["state"]) == ("二人称", "完結")
    assert (result["start"], result["end"]) == ("1201/01/01 00:00:00", "1299/01/01 00:00:00")
    assert result["event_seeded"] is False
