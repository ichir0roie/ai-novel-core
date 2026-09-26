"""週次ルーチンで Todoist のタスクにする、ユーザの判断が要るものの一覧(`ListPendingReviews`)。"""
from ai.claude_code.interface.review.list_pending_reviews import ListPendingReviews
from ai.time_keeper import idea_context
from db.schema import (
    Episode, EpisodeText, Event, Idea, Location, Story,
)
from db.stamp import Stamp


def test_nothing_to_review_on_an_empty_world(session):
    assert ListPendingReviews().run() == []


def test_candidate_idea_is_listed_with_where_it_came_from(session):
    event = Event(name="峠越え", text="", time=Stamp(2100))
    candidate = Idea(name="宿り", kind="技術", auto_generated=True, text="体に虫を宿す治療",
                     directory_path="技術")
    session.add_all([event, candidate, Idea(name="魔力", kind="技術", text="")])
    session.commit()
    idea_context.link(session, event, [candidate])
    session.commit()

    [item] = ListPendingReviews().run()

    assert item["key"] == f"idea:{candidate.id}"
    assert item["kind"] == "候補"
    assert "「宿り」" in item["title"]
    assert "体に虫を宿す治療" in item["detail"]
    assert f"event「峠越え」(id={event.id})" in item["detail"]
    assert f"md: worlds/idea/技術/{candidate.id}_宿り.md" in item["detail"]
    assert f"MergeIdea({candidate.id}, " in item["detail"]


def test_written_but_unsynced_episode_is_listed_and_seed_only_one_is_not(session):
    place = Location(name="村", kind="村", text="")
    session.add(place)
    session.flush()
    story = Story(name="村の話", place_id=place.id, text="", narration="", state="執筆中")
    session.add(story)
    session.flush()
    written = Episode(story_id=story.id, title="旅立ち", synced=False, episode_text=EpisodeText(text="本文"))
    session.add_all([
        written,
        Episode(story_id=story.id, title="", key="種だけ", synced=False),
        Episode(story_id=story.id, title="済み", synced=True, episode_text=EpisodeText(text="本文")),
    ])
    session.commit()

    [item] = ListPendingReviews().run()

    assert item["key"] == f"episode:{written.id}"
    assert item["title"] == "村の話「旅立ち」を世界観へ反映して synced を立てる"
    assert f"SetEpisodeSynced({written.id})" in item["detail"]
    # 話の md は作品の md と同じ名前のディレクトリの下にある
    assert f"md: worlds/story/{story.id}_村の話/{story.id}__旅立ち.md" in item["detail"]


def test_todo_left_in_a_text_is_listed_with_its_lines(session):
    idea = Idea(name="大災厄", kind="概念", text="<!-- TODO イベントに移動? -->\n\n本文",
                directory_path="ファンタジー")
    session.add_all([idea, Idea(name="魔力", kind="技術", text="TOD だけ")])
    session.commit()

    [item] = ListPendingReviews().run()

    assert item["key"] == f"todo:idea:{idea.id}"
    assert item["detail"].splitlines() == [
        "<!-- TODO イベントに移動? -->", f"md: worlds/idea/ファンタジー/{idea.id}_大災厄.md"]
