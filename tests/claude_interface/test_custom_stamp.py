"""作品の暦(`custom_stamp`)を付けた作品の時刻の出し入れと、西暦で入れてきた時刻の読み替え。"""
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from gui.api import interface
from gui.api.app import app
from data_access_logic.story import scope
from db import writer
from db.schema import (
    Character, CharacterHistory, CharacterSkill, CustomStamp, Episode, Event, Expansion, ExpansionChange, Idea,
    IdeaHistory, Location, Story, get_env_session,
)
from db.stamp import Stamp, using_calendar

CALENDAR = {"name": "テスト長日暦", "offset": "5000/01/01", "hours_per_day": 27, "days_per_week": 7,
            "months": [{"days": 31}] * 12}


def _call(entrance_id: str, args: dict, story_id: int | None = None):
    return interface.call(interface.entrance_class(entrance_id), args, story_id)


@dataclass
class Saga:
    custom_stamp_id: int
    story_id: int
    chapter_id: int


@pytest.fixture
def saga() -> Iterator[Saga]:
    custom_stamp = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": CALENDAR})
    with get_env_session() as s:
        story = Story(name="テスト長日の物語", text="", custom_stamp_id=custom_stamp["id"])
        s.add(story)
        s.flush()
        chapter = Story(name="テスト長日の章", text="", parent_story_id=story.id)
        s.add(chapter)
        s.commit()
        yield Saga(custom_stamp_id=custom_stamp["id"], story_id=story.id, chapter_id=chapter.id)


def test_commit_custom_stamp_numbers_months():
    record = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": CALENDAR})

    assert record["offset"] == "5000/01/01 00:00:00"
    assert [month["number"] for month in record["months"]] == list(range(1, 13))


def test_commit_custom_stamp_rejects_offset_outside_the_calendar():
    with pytest.raises(ValueError):
        _call("custom_stamp.commit_custom_stamp.CommitCustomStamp",
              {"custom_stamp": {**CALENDAR, "months": [{"days": 30}] * 12, "offset": "5000/01/31"}})


def test_episode_times_are_read_and_shown_in_the_calendar_of_the_chapter(saga):
    record = _call("episode.commit_episode.CommitEpisode",
                   {"episode": {"story_id": saga.chapter_id, "title": "長い夜", "start": "11592/03/15 26:00:00"}})

    assert record["start"] == "11592/03/15 26:00:00"
    with get_env_session() as s:
        stored = s.get_one(Episode, record["id"]).start
    assert stored is not None and stored.western_text() != "11592/03/15 26:00:00"


def test_new_character_is_placed_in_the_story_of_its_scope(saga):
    record = _call("character.commit_character.CommitCharacter",
                   {"character": {"name": "テスト長日の旅人", "start": "11570/02/31",
                                  "histories": [{"start": "11590/05/05 25:00:00", "description": "夜更けに港へ着く"}]}},
                   saga.story_id)

    assert record["start"] == "11570/02/31 00:00:00"
    with get_env_session() as s:
        character = s.get_one(Character, record["id"])
        assert character.story_id == saga.story_id


def test_history_entrance_reads_time_in_the_calendar_of_the_owner(saga):
    character = _call("character.commit_character.CommitCharacter",
                      {"character": {"name": "テスト長日の書記", "story_id": saga.story_id,
                                     "histories": [{"start": "11590/01/01", "description": "書記になる"}]}})
    history_id = character["histories"][0]["id"]

    changed = _call("character.update_history.UpdateCharacterHistory",
                    {"history_id": history_id, "history": {"start": "11590/12/31 26:00:00", "description": "書記になる"}})

    assert changed["start"] == "11590/12/31 26:00:00"


def test_api_shows_rows_in_their_story_calendar(saga):
    record = _call("episode.commit_episode.CommitEpisode",
                   {"episode": {"story_id": saga.story_id, "title": "長い昼", "start": "11592/01/01 25:00:00"}})
    with TestClient(app) as client:
        shown = client.get(f"/api/tables/episode/records/{record['id']}").json()
        scope = client.get("/api/scope", params={"table": "episode", "id": record["id"]}).json()
        chosen = client.get("/api/scope", headers={"x-novel-story": str(saga.chapter_id)}).json()

    assert shown["record"]["start"] == "11592/01/01 25:00:00"
    assert scope["story_id"] == saga.story_id
    assert scope["calendar"]["hours_per_day"] == 27
    assert chosen["story_id"] == saga.chapter_id and chosen["calendar"]["month_days"] == [31] * 12


def test_shift_moves_western_digits_into_the_calendar_without_touching_updated_at():
    with get_env_session() as s:
        story = Story(name="テスト読み替えの物語", text="")
        s.add(story)
        s.flush()
        episode = Episode(story_id=story.id, title="読み替え", start="11592/03/15 10:00:00", end="4999/01/01")
        character = Character(name="テスト読み替えの人", story_id=story.id,
                              histories=[CharacterHistory(start="11580/02/30", description="生まれる")])
        idea = Idea(name="テスト読み替えの術", kind="技術", text="", story_id=story.id,
                    histories=[IdeaHistory(start="11500", name="術")])
        s.add_all([episode, character, idea])
        s.commit()
        ids = (story.id, episode.id, character.id, idea.id)
        updated_at = episode.updated_at
    custom_stamp = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": CALENDAR})
    with get_env_session() as s:
        s.get_one(Story, ids[0]).custom_stamp_id = custom_stamp["id"]
        s.commit()

    planned = _call("custom_stamp.shift_into_custom_stamp.ShiftIntoCustomStamp", {"custom_stamp_id": custom_stamp["id"]})
    with get_env_session() as s:
        assert s.get_one(Episode, ids[1]).start == Stamp.western(11592, 3, 15, 10)
    shifted = _call("custom_stamp.shift_into_custom_stamp.ShiftIntoCustomStamp",
                    {"custom_stamp_id": custom_stamp["id"], "dry_run": False})

    assert planned["shifted"] == shifted["shifted"] == {"episode": 1, "character_history": 1, "idea_history": 1}
    assert shifted["story_ids"] == [ids[0]]
    episode = _call("episode.read_episodes.ReadEpisodes", {"story_id": ids[0]})
    # 日付は桁のまま、時刻は一日のうちの割合を保って移る(27 時間の一日の 11:15 は、24 時間の一日の 10:00)
    assert episode[0]["start"] == "11592/03/15 11:15:00"
    with get_env_session() as s:
        row = s.get_one(Episode, ids[1])
        assert row.updated_at == updated_at
        # 暦の始まりより前の時刻は動かさない
        assert row.end == Stamp.western(4999, 1, 1)
        assert row.start != Stamp.western(11592, 3, 15, 10)


def test_place_in_story_keeps_updated_at():
    with get_env_session() as s:
        story = Story(name="テスト置き場", text="")
        idea = Idea(name="テスト置かれる術", kind="技術", text="")
        s.add_all([story, idea])
        s.commit()
        story_id, idea_id, updated_at = story.id, idea.id, idea.updated_at

    _call("story.place_in_story.PlaceInStory", {"story_id": story_id, "table": "idea", "ids": [idea_id]})

    with get_env_session() as s:
        idea = s.scalars(select(Idea).where(Idea.id == idea_id)).one()
        assert idea.story_id == story_id
        assert idea.updated_at == updated_at


def test_custom_stamp_rows_are_listed_in_the_gui():
    with TestClient(app) as client:
        created = client.post("/api/tables/custom_stamp/records", json=CALENDAR)
        listed = client.get("/api/tables/custom_stamp/records", params={"order": "desc"}).json()

    assert created.status_code == 201, created.text
    assert created.json()["record"]["offset"] == "5000/01/01 00:00:00"
    assert any(item["id"] == created.json()["record"]["id"] for item in listed["items"])
    with get_env_session() as s:
        assert s.get(CustomStamp, created.json()["record"]["id"]) is not None


def test_shift_counts_digits_outside_the_calendar_and_moves_revert_snapshots():
    # 30 日の月の暦では、西暦で入れた 31 日は暦に無いので移さずに数える
    custom_stamp = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp",
                         {"custom_stamp": {**CALENDAR, "months": [{"days": 30}] * 12}})
    with get_env_session() as s:
        story = Story(name="テスト三十日の物語", text="", custom_stamp_id=custom_stamp["id"])
        s.add(story)
        s.flush()
        valid = Episode(story_id=story.id, title="十五日", start="11592/03/15 10:00:00")
        invalid = Episode(story_id=story.id, title="三十一日", start="11592/03/31 10:00:00")
        s.add_all([valid, invalid])
        s.flush()
        expansion = Expansion(mode="author", story_id=story.id)
        s.add(expansion)
        s.flush()
        # 取り消しの控えは、暦を付ける前に西暦の表記で書かれている
        change = ExpansionChange(expansion_id=expansion.id, table_name="episode", row_id=valid.id, op="update",
                                 before={"title": "十五日", "start": "11592/03/14 10:00:00"}, reason="")
        s.add(change)
        s.commit()
        ids = (valid.id, invalid.id, change.id)

    planned = _call("custom_stamp.shift_into_custom_stamp.ShiftIntoCustomStamp", {"custom_stamp_id": custom_stamp["id"]})
    shifted = _call("custom_stamp.shift_into_custom_stamp.ShiftIntoCustomStamp",
                    {"custom_stamp_id": custom_stamp["id"], "dry_run": False})

    assert planned["invalid"] == shifted["invalid"] == {"episode": 1}
    assert shifted["invalid_samples"][0]["id"] == ids[1]
    assert shifted["shifted"] == {"episode": 1, "expansion_change.episode": 1}
    with get_env_session() as s:
        assert s.get_one(Episode, ids[1]).start == Stamp.western(11592, 3, 31, 10)
        moved = s.get_one(ExpansionChange, ids[2]).before
        assert moved is not None and moved["title"] == "十五日"
        # 控えは移したあとも西暦の表記で、暦では同じ桁を指す
        with using_calendar(None):
            kept = Stamp.parse(moved["start"])
        assert kept is not None and kept != Stamp.western(11592, 3, 14, 10)
        with using_calendar(scope.calendar_of_row(s.get_one(CustomStamp, custom_stamp["id"]))):
            assert str(kept) == "11592/03/14 11:15:00"


def test_story_comes_from_the_row_written_before_nested_references(saga):
    with get_env_session() as s:
        other = Story(name="テスト別の物語", text="")
        s.add(other)
        s.flush()
        place = Location(name="テスト別の村", kind="村", text="", story_id=other.id)
        own = Character(name="テスト長日の鍛冶", kind="人物", story_id=saga.story_id)
        stranger = Character(name="テスト別の旅人", kind="人物", story_id=other.id)
        s.add_all([place, own, stranger])
        s.flush()
        history = CharacterHistory(character_id=own.id, start="1200", description="鍛冶場を開く")
        skill = CharacterSkill(character_id=own.id, name="鎚", kind="技", text="")
        happening = Event(name="テスト長日の祭り", text="", hidden=False, time="1200", story_id=saga.story_id,
                          location_id=place.id)
        s.add_all([history, skill, happening])
        s.commit()

        # 関係・スキル・場所の欄は、表の名前から引く
        assert scope.story_of_args(s, {"relation": {"character_1_id": own.id, "character_2_id": stranger.id}}) == saga.story_id
        assert scope.story_of_args(s, {"character_skill_id": skill.id, "history": {"description": "x"}}) == saga.story_id
        assert scope.story_of_args(s, {"location_ids": [place.id], "time": "1200"}) == other.id
        # 書く行(来歴・出来事)の作品が、入れ子の参照(知る相手・場所)より先に効く
        assert scope.story_of_args(s, {"history_id": history.id, "history": {"knowers": [{"knower_id": stranger.id}]}},
                                   CharacterHistory) == saga.story_id
        assert scope.story_of_args(s, {"event": {"id": happening.id, "location_id": place.id}}) == saga.story_id


def test_rewrites_keep_ai_rows_ai():
    custom_stamp = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": CALENDAR})
    with get_env_session() as s:
        story = Story(name="テスト AI の行の物語", text="")
        s.add(story)
        s.flush()
        with writer.generated():
            idea = Idea(name="テスト AI の術", kind="技術", text="", histories=[IdeaHistory(start="11500", name="術")])
            s.add(idea)
            s.flush()
        s.commit()
        assert idea.origin == "ai"
        story_id, idea_id = story.id, idea.id

    _call("story.place_in_story.PlaceInStory", {"story_id": story_id, "table": "idea", "ids": [idea_id]})
    with get_env_session() as s:
        s.get_one(Story, story_id).custom_stamp_id = custom_stamp["id"]
        s.commit()
    shifted = _call("custom_stamp.shift_into_custom_stamp.ShiftIntoCustomStamp",
                    {"custom_stamp_id": custom_stamp["id"], "dry_run": False})

    assert shifted["shifted"] == {"idea_history": 1}
    with get_env_session() as s:
        idea = s.get_one(Idea, idea_id)
        # 中身を変えない書き直しなので、AI の行は AI の行のまま
        assert (idea.story_id, idea.origin) == (story_id, "ai")
        assert s.scalars(select(IdeaHistory).where(IdeaHistory.idea_id == idea_id)).one().origin == "ai"


def test_batch_results_are_written_in_each_request_calendar(saga):
    character = _call("character.commit_character.CommitCharacter",
                      {"character": {"name": "テスト長日の写字生", "story_id": saga.story_id,
                                     "histories": [{"start": "11590/01/01", "description": "写字を習う"}]}})
    history_id = character["histories"][0]["id"]

    # 呼ぶ側が作品を渡さなくても、リクエストの作品の暦で読み、同じ暦で返す
    [changed] = _call("batch.run_batch.RunBatch", {"requests": [
        {"entrance": "character.update_history.UpdateCharacterHistory",
         "args": {"history_id": history_id, "history": {"start": "11590/12/31 26:00", "description": "写字を習う"}}}]})

    assert changed["start"] == "11590/12/31 26:00:00"
