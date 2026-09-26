import pytest

from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story.delete_story import DeleteStory
from ai.claude_code.interface.story.list_stories import ListStories
from ai.claude_code.interface.story.list_unsynced_episodes import ListUnsyncedEpisodes
from ai.claude_code.interface.story.read_brief import ReadBrief
from ai.claude_code.interface.story.read_cast import ReadCast
from ai.claude_code.interface.story.read_episodes import ReadEpisodes
from ai.claude_code.interface.story.read_surroundings import ReadSurroundings
from ai.claude_code.interface.story.set_episode_synced import SetEpisodeSynced
from ai.claude_code.interface.story.start_story import StartStory
from data_access_logic.query.common_query import NotFoundError
from db.schema import Character, CharacterPlace, Episode, EpisodeText, Event, EventCharacter, Location, Story
from db.stamp import Stamp


@pytest.fixture
def world(session):
    planet = Location(name="ノウル", kind="星", text="")
    session.add(planet)
    session.flush()
    village = Location(name="村", kind="村", text="", parent_id=planet.id)
    session.add(village)
    session.flush()
    house = Location(name="家", kind="建物", text="", parent_id=village.id)
    session.add(house)
    session.flush()
    story = Story(name="村の話", place_id=village.id, text="", narration="三人称", state="構想中",
                  start=Stamp(2100))
    alice = Character(name="アル", text="")
    bell = Character(name="ベル", text="")
    session.add_all([story, alice, bell])
    session.flush()
    session.add_all([
        CharacterPlace(character_id=alice.id, location_id=village.id, start=Stamp(2000)),
        CharacterPlace(character_id=bell.id, location_id=house.id, start=Stamp(2000)),
    ])
    session.commit()
    return {"planet": planet.id, "village": village.id, "house": house.id,
            "story": story.id, "alice": alice.id, "bell": bell.id}


def _episodes(session, story_id, numbers, *, synced=True):
    for number in numbers:
        session.add(Episode(story_id=story_id, start=Stamp(2100, 1, number), title=f"第{number}話",
                            synced=synced, episode_text=EpisodeText(text=f"本文{number}")))
    session.commit()


def test_list_stories_counts_episodes(session, world):
    _episodes(session, world["story"], [1, 2])
    _episodes(session, world["story"], [3], synced=False)

    stories = ListStories().run()
    assert len(stories) == 1
    assert stories[0]["name"] == "村の話"
    assert stories[0]["place_name"] == "村"
    assert stories[0]["episode_count"] == 3
    assert stories[0]["last_episode"]["title"] == "第3話"
    assert [row["title"] for row in stories[0]["unsynced"]] == ["第3話"]


def test_delete_story_returns_deleted_row(session, world):
    deleted = DeleteStory(world["story"]).run()
    assert deleted["id"] == world["story"]
    assert deleted["name"] == "村の話"
    assert deleted["place_id"] == world["village"]
    session.expire_all()
    assert session.get(Story, world["story"]) is None


def test_delete_story_refuses_story_with_episodes(session, world):
    _episodes(session, world["story"], [1])
    with pytest.raises(ValueError):
        DeleteStory(world["story"]).run()
    session.expire_all()
    assert session.get(Story, world["story"]) is not None


def test_delete_story_rejects_unknown_id():
    with pytest.raises(UnknownRecordError):
        DeleteStory(9999).run()


def test_read_episodes_returns_latest_in_order(session, world):
    _episodes(session, world["story"], range(1, 6))

    assert [e["title"] for e in ReadEpisodes(world["story"], count=3).run()] == ["第3話", "第4話", "第5話"]
    assert [e["title"] for e in ReadEpisodes(world["story"], count=2, before="2100/01/04").run()] == [
        "第2話", "第3話"]
    assert ReadEpisodes(world["story"], count=1).run()[0]["text"] == "本文5"
    assert "text" not in ReadEpisodes(world["story"], count=1, text=False).run()[0]


def test_read_episodes_rejects_unknown_story():
    with pytest.raises(NotFoundError):
        ReadEpisodes(9999).run()


def test_list_unsynced_episodes(session, world):
    other = Story(name="別の話", place_id=world["village"], text="", narration="", state="構想中")
    session.add(other)
    session.commit()
    _episodes(session, world["story"], [1])
    _episodes(session, world["story"], [2], synced=False)
    _episodes(session, other.id, [1], synced=False)

    rows = ListUnsyncedEpisodes().run()
    assert [(row["story_id"], row["title"]) for row in rows] == [(world["story"], "第2話"), (other.id, "第1話")]
    assert rows[0]["story_name"] == "村の話"
    assert rows[0]["start"] == "2100/01/02 00:00:00"
    assert [row["title"] for row in ListUnsyncedEpisodes(world["story"]).run()] == ["第2話"]


def test_set_episode_synced_toggles_flag(session, world):
    _episodes(session, world["story"], [1], synced=False)
    episode_id = session.query(Episode).one().id

    assert SetEpisodeSynced(episode_id).run()["synced"] is True
    assert ListUnsyncedEpisodes(world["story"]).run() == []
    assert SetEpisodeSynced(episode_id, False).run()["synced"] is False
    assert [row["id"] for row in ListUnsyncedEpisodes(world["story"]).run()] == [episode_id]


def test_set_episode_synced_rejects_missing_episode(world):
    with pytest.raises(UnknownRecordError):
        SetEpisodeSynced(9999).run()


def test_read_brief_hides_hidden_events(session, world):
    session.add_all([
        Event(name="祭り", text="", location_id=world["house"], time=Stamp(2100, 5, 1)),
        Event(name="密談", text="", location_id=world["village"], time=Stamp(2100, 6, 1), hidden=True),
        Event(name="遠い昔", text="", location_id=world["village"], time=Stamp(1900)),
        Event(name="先の話", text="", location_id=world["village"], time=Stamp(2101)),
    ])
    session.commit()

    brief = ReadBrief(world["village"], "2100").run()
    assert [p["name"] for p in brief["path"]] == ["ノウル", "村"]
    assert brief["time"] == "2100/12/31 23:59:59"
    assert [e["name"] for e in brief["recent_events"]] == ["祭り"]
    assert sorted(c["name"] for c in brief["present_characters"]) == ["アル", "ベル"]

    full = ReadBrief(world["village"], "2100", full=True).run()
    assert [e["name"] for e in full["recent_events"]] == ["密談", "祭り"]


def test_read_brief_requires_time(world):
    with pytest.raises(ValueError):
        ReadBrief(world["village"], None).run()


def test_read_cast_climbs_levels(session, world):
    story = Story(name="家の話", place_id=world["house"], text="", narration="", state="構想中",
                  start=Stamp(2100))
    session.add(story)
    session.commit()

    cast = ReadCast(story.id, levels=0).run()
    assert cast["scope"]["name"] == "家"
    assert [c["name"] for c in cast["characters"]] == ["ベル"]

    cast = ReadCast(story.id, levels=1).run()
    assert cast["scope"]["name"] == "村"
    assert cast["time"] == "2100/12/31 23:59:59"
    assert sorted(c["name"] for c in cast["characters"]) == ["アル", "ベル"]


def test_read_cast_requires_place(session):
    story = Story(name="場所の無い話", text="", narration="", state="構想中", start=Stamp(2100))
    session.add(story)
    session.commit()
    with pytest.raises(ValueError):
        ReadCast(story.id).run()


def test_read_surroundings_collects_neighbors_and_events(session, world):
    event = Event(name="再会", text="", location_id=world["house"], time=Stamp(2100, 3, 1))
    event.event_characters = [EventCharacter(character_id=world["alice"])]
    session.add(event)
    session.commit()

    around = ReadSurroundings(world["alice"], "2100").run()
    assert around["character_id"] == world["alice"]
    assert sorted(c["name"] for c in around["characters"]) == ["アル", "ベル"]
    assert [e["name"] for e in around["events"]] == ["再会"]
    assert around["events"][0]["characters"] == [{"id": world["alice"], "name": "アル"}]


def test_read_surroundings_requires_time(world):
    with pytest.raises(ValueError):
        ReadSurroundings(world["alice"], None)


def test_start_story_stops_on_unsynced_episode(session, world):
    _episodes(session, world["story"], [1], synced=False)

    result = StartStory(world["story"]).run()
    assert result["stopped"] is True
    assert [row["title"] for row in result["unsynced"]] == ["第1話"]
    assert "message" in result
    assert "cast" not in result

    result = StartStory(world["story"], skip_sync=True).run()
    assert result["stopped"] is False
    assert "cast" in result


def test_start_story_gathers_materials(session, world):
    _episodes(session, world["story"], [1, 2])

    result = StartStory(world["story"], episodes=1).run()
    assert result["stopped"] is False
    assert result["story"]["name"] == "村の話"
    assert result["time"] == "2100/12/31 23:59:59"
    assert [e["title"] for e in result["episodes"]] == ["第2話"]
    assert sorted(c["name"] for c in result["cast"]["characters"]) == ["アル", "ベル"]
    assert result["brief"]["place"]["name"] == "村"


def test_start_story_rejects_unknown_story():
    with pytest.raises(NotFoundError):
        StartStory(9999).run()
