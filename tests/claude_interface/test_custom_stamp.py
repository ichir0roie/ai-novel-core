"""行の暦(`custom_stamp`)での時刻の出し入れ。暦は持ち主の行が持ち、作品の暦は新しい行の既定。"""
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
    Character, CharacterHistory, CharacterSkill, CustomStamp, Episode, Event, EventCharacter, Idea, IdeaHistory, Location, Story,
    get_env_session, western_stamp_id,
)

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
        chapter = Story(name="テスト長日の章", text="", parent_story_id=story.id, custom_stamp_id=custom_stamp["id"])
        s.add(chapter)
        s.commit()
        yield Saga(custom_stamp_id=custom_stamp["id"], story_id=story.id, chapter_id=chapter.id)


def test_commit_custom_stamp_numbers_months():
    record = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": CALENDAR})

    assert record["offset"] == "5000/01/01 00:00:00"
    assert [month["number"] for month in record["months"]] == list(range(1, 13))


def test_commit_custom_stamp_rejects_an_offset_that_is_not_a_western_time():
    with pytest.raises(ValueError):
        _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": {**CALENDAR, "offset": "5000/13/01"}})


def test_new_episode_takes_the_calendar_of_its_story(saga):
    record = _call("episode.commit_episode.CommitEpisode",
                   {"episode": {"story_id": saga.chapter_id, "title": "長い夜", "start": "1592/03/15 26:00:00"}})

    assert record["start"] == "1592/03/15 26:00:00"
    assert record["custom_stamp_id"] == saga.custom_stamp_id
    with get_env_session() as s:
        stored = s.get_one(Episode, record["id"]).start
    # 暦の 0 年 1 月 1 日が西暦 5000 年 1 月 1 日。一日は地球の 27 時間なので、1592 年は西暦の 6000 年台
    assert stored is not None and stored.western_digits[0] > 6000


def test_new_character_is_placed_in_the_story_of_its_scope(saga):
    record = _call("character.commit_character.CommitCharacter",
                   {"character": {"name": "テスト長日の旅人", "start": "1570/02/31",
                                  "histories": [{"start": "1590/05/05 25:00:00", "description": "夜更けに港へ着く"}]}},
                   saga.story_id)

    assert record["start"] == "1570/02/31 00:00:00"
    with get_env_session() as s:
        character = s.get_one(Character, record["id"])
        assert (character.story_id, character.custom_stamp_id) == (saga.story_id, saga.custom_stamp_id)


def test_history_entrance_reads_time_in_the_calendar_of_the_owner(saga):
    character = _call("character.commit_character.CommitCharacter",
                      {"character": {"name": "テスト長日の書記", "story_id": saga.story_id,
                                     "histories": [{"start": "1590/01/01", "description": "書記になる"}]}})
    history_id = character["histories"][0]["id"]

    changed = _call("character.update_history.UpdateCharacterHistory",
                    {"history_id": history_id, "history": {"start": "1590/12/31 26:00:00", "description": "書記になる"}})

    assert changed["start"] == "1590/12/31 26:00:00"


def test_api_shows_each_row_in_its_own_calendar(saga):
    long_day = _call("episode.commit_episode.CommitEpisode",
                     {"episode": {"story_id": saga.story_id, "title": "長い昼", "start": "1592/01/01 25:00:00"}})
    with get_env_session() as s:
        western_id = western_stamp_id(s)
    # 同じ作品でも、西暦の行は西暦で読み書きする
    earth = _call("episode.commit_episode.CommitEpisode",
                  {"episode": {"story_id": saga.story_id, "custom_stamp_id": western_id, "title": "地球の朝",
                               "start": "4990/06/01 08:00:00"}})
    with TestClient(app) as client:
        shown = client.get(f"/api/tables/episode/records/{long_day['id']}").json()
        found = client.get("/api/scope", params={"table": "episode", "id": earth["id"]}).json()
        chosen = client.get("/api/scope", headers={"x-novel-story": str(saga.chapter_id)}).json()
        listed = client.get("/api/tables/episode/records", params={"story_id": saga.story_id}).json()

    assert shown["record"]["start"] == "1592/01/01 25:00:00"
    assert earth["start"] == "4990/06/01 08:00:00"
    assert found["custom_stamp_id"] == western_id and found["calendar"] is None
    assert chosen["story_id"] == saga.chapter_id and chosen["calendar"]["month_days"] == [31] * 12
    starts = {item["id"]: item["start"] for item in listed["items"]}
    assert starts == {long_day["id"]: "1592/01/01 25:00:00", earth["id"]: "4990/06/01 08:00:00"}


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
        happening = Event(name="テスト長日の祭り", text="", hidden=False, time="1200",
                          event_characters=[EventCharacter(character_id=own.id)])
        s.add_all([history, skill, happening])
        s.commit()

        # 関係・スキル・場所の欄は、表の名前から引く
        assert scope.story_of_args(s, {"relation": {"character_1_id": own.id, "character_2_id": stranger.id}}) == saga.story_id
        assert scope.story_of_args(s, {"character_skill_id": skill.id, "history": {"description": "x"}}) == saga.story_id
        assert scope.story_of_args(s, {"location_ids": [place.id], "time": "1200"}) == other.id
        # 書く行(来歴・出来事)の作品が、入れ子の参照(知る相手・場所)より先に効く。出来事の作品は当事者の作品
        assert scope.story_of_args(s, {"history_id": history.id, "history": {"knowers": [{"knower_id": stranger.id}]}},
                                   CharacterHistory) == saga.story_id
        assert scope.story_of_args(s, {"event": {"id": happening.id, "location_id": place.id}}) == saga.story_id


def test_rewrites_keep_ai_rows_ai():
    with get_env_session() as s:
        story = Story(name="テスト AI の行の物語", text="")
        s.add(story)
        s.flush()
        with writer.generated():
            idea = Idea(name="テスト AI の術", kind="技術", text="", histories=[IdeaHistory(start="1500", name="術")])
            s.add(idea)
            s.flush()
        s.commit()
        assert idea.origin == "ai"
        story_id, idea_id = story.id, idea.id

    _call("story.place_in_story.PlaceInStory", {"story_id": story_id, "table": "idea", "ids": [idea_id]})

    with get_env_session() as s:
        idea = s.get_one(Idea, idea_id)
        # 中身を変えない書き直しなので、AI の行は AI の行のまま
        assert (idea.story_id, idea.origin) == (story_id, "ai")
        assert s.scalars(select(IdeaHistory).where(IdeaHistory.idea_id == idea_id)).one().origin == "ai"


def test_batch_results_are_written_in_each_request_calendar(saga):
    character = _call("character.commit_character.CommitCharacter",
                      {"character": {"name": "テスト長日の写字生", "story_id": saga.story_id,
                                     "histories": [{"start": "1590/01/01", "description": "写字を習う"}]}})
    history_id = character["histories"][0]["id"]

    # 呼ぶ側が作品を渡さなくても、リクエストの行の暦で読み、同じ暦で返す
    [changed] = _call("batch.run_batch.RunBatch", {"requests": [
        {"entrance": "character.update_history.UpdateCharacterHistory",
         "args": {"history_id": history_id, "history": {"start": "1590/12/31 26:00", "description": "写字を習う"}}}]})

    assert changed["start"] == "1590/12/31 26:00:00"


def test_character_options_give_the_birth_in_the_character_calendar(saga):
    character = _call("character.commit_character.CommitCharacter",
                      {"character": {"name": "テスト長日の少年", "story_id": saga.story_id, "start": "1574/01/01"}})
    with TestClient(app) as client:
        # 西暦で数える作品を選んでいても、選択肢の生まれは人物の暦で書く(画面は話の時刻から歳を数える)
        options = client.get("/api/tables/character/options", params={"ids": character["id"]},
                             headers={"x-novel-story": "none"}).json()

    assert [option["born"] for option in options["items"]] == ["1574/01/01 00:00:00"]
