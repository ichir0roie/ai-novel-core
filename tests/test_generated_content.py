from ai.time_keeper import event_summary, generated_content
from db.schema import Episode, EpisodeSummary, EpisodeText, Event, EventSummary, Idea, Location, Story
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


def test_refresh_without_a_record_only_tends_to_memes(session):
    idea = Idea(name="語", kind="用語", text="語の説明")
    session.add(idea)
    session.commit()
    ai = MockAIClient(seed=1)

    result = generated_content.refresh(session, ai)

    assert result == {"memes_added": 0, "summarized": False}
    assert idea.meme_seeded


def test_refresh_summarizes_the_given_event(session):
    event = Event(name="出来事", text="本文", time=Stamp(2100))
    session.add(event)
    session.commit()
    ai = MockAIClient(seed=1)

    result = generated_content.refresh(session, ai, event)

    assert result["summarized"] is True
    assert session.query(EventSummary).filter_by(event_id=event.id).count() == 1


def test_refresh_summarizes_the_given_episode(session):
    place = Location(name="村", kind="村", text="")
    session.add(place)
    session.flush()
    story = Story(name="作品", place_id=place.id, text="", narration="", state="")
    session.add(story)
    session.flush()
    episode = Episode(story_id=story.id, title="第一話", episode_text=EpisodeText(text="本文"))
    session.add(episode)
    session.commit()
    ai = MockAIClient(seed=1)

    result = generated_content.refresh(session, ai, episode)

    assert result["summarized"] is True
    assert session.query(EpisodeSummary).filter_by(episode_id=episode.id).count() == 1


def test_refresh_skips_summary_for_a_record_without_text(session):
    event = Event(name="出来事", text="", time=Stamp(2100))
    session.add(event)
    session.commit()
    ai = MockAIClient(seed=1)

    result = generated_content.refresh(session, ai, event)

    assert result["summarized"] is False
    assert session.query(EventSummary).count() == 0


def test_refresh_all_catches_up_events_and_episodes_missing_a_summary(session):
    place = Location(name="村", kind="村", text="")
    session.add(place)
    session.flush()
    story = Story(name="作品", place_id=place.id, text="", narration="", state="")
    session.add(story)
    session.flush()
    summarized_event = Event(name="出来事1", text="本文1", time=Stamp(2100))
    unsummarized_event = Event(name="出来事2", text="本文2", time=Stamp(2101))
    empty_event = Event(name="出来事3", text="", time=Stamp(2102))
    episode = Episode(story_id=story.id, title="第一話", episode_text=EpisodeText(text="本文"))
    session.add_all([summarized_event, unsummarized_event, empty_event, episode])
    session.commit()
    event_summary.summarize(session, summarized_event, MockAIClient(seed=1))

    result = generated_content.refresh_all(session, MockAIClient(seed=2))

    assert result["events_summarized"] == 2
    assert result["episodes_summarized"] == 1
    assert session.query(EventSummary).filter_by(event_id=unsummarized_event.id).count() == 1
    assert session.query(EpisodeSummary).filter_by(episode_id=episode.id).count() == 1
    assert session.query(EventSummary).filter_by(event_id=empty_event.id).count() == 0
