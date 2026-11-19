"""暦のある作品で、人物役が受け取る今の時刻と物事の古さ(`character/time_sense.py`)。年の数は渡さない。"""
import json
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from data_access_logic.episode_session.store import SessionStore
from data_access_logic.step import run_json
from db.guard import _jsonable, restored_value
from db.schema import (
    Character, CharacterHistory, CharacterHistoryKnower, CharacterLocation, CharacterParameter, CharacterSkill, CharacterSkillHistory,
    CharacterSpeech, Episode, EpisodeCharacter, Event, Location, Story, get_env_session,
)
from db.stamp import Calendar, Stamp, using_calendar
from gui.api import interface

CALENDAR = {"name": "テスト長日暦", "offset": "5000/01/01", "hours_per_day": 27, "days_per_week": 7,
            "months": [{"days": 31}] * 12}


def _call(entrance_id: str, args: dict, story_id: int | None = None):
    return interface.call(interface.entrance_class(entrance_id), args, story_id)


@dataclass
class LongDay:
    calendar: Calendar
    story_id: int
    character_id: int
    episode_id: int


@pytest.fixture
def long_day() -> Iterator[LongDay]:
    """一日 27 時間の暦の作品に、人物が一人いる話。"""
    record = _call("custom_stamp.commit_custom_stamp.CommitCustomStamp", {"custom_stamp": CALENDAR})
    calendar = Calendar(offset=(5000, 1, 1, 0, 0, 0), month_days=(31,) * 12, hours_per_day=27, days_per_week=7,
                        name="テスト長日暦", month_names=("",) * 12)
    with using_calendar(calendar), get_env_session() as s:
        story = Story(name="テスト長日の暮らし", text="", custom_stamp_id=record["id"])
        s.add(story)
        s.flush()
        town = Location(name="テスト長日の町", kind="町", text="", story_id=story.id)
        s.add(town)
        s.flush()
        character = Character(
            name="テスト長日の娘", kind="人物", story_id=story.id,
            parameters=[CharacterParameter(start="11570/02/31", sex="女")],
            locations=[CharacterLocation(location_id=town.id, start="11570/02/31")])
        s.add(character)
        s.flush()
        # 来歴は知る相手(本人)に当たる行だけが渡る
        character.histories = [
            CharacterHistory(start="11592/03/14 20:00", description="門番に呼び止められる",
                             knowers=[CharacterHistoryKnower(knower_id=character.id)]),
            CharacterHistory(start="11589/05/01", kind="持ち物", description="祖父の短刀",
                             knowers=[CharacterHistoryKnower(knower_id=character.id)])]
        s.add(CharacterSkill(character_id=character.id, name="外套", kind="装い", text="", histories=[
            CharacterSkillHistory(start="11591/03/15 26:00", description="灰色の外套")]))
        previous = Episode(story_id=story.id, title="前の夜", plot_text="", main_text="", start="11592/02/10 10:00")
        episode = Episode(story_id=story.id, title="長い夜", plot_text="", main_text="", start="11592/03/15 26:00",
                          location_id=town.id)
        s.add_all([previous, episode])
        s.flush()
        s.add(EpisodeCharacter(episode_id=episode.id, character_id=character.id))
        s.add(CharacterSpeech(episode_id=previous.id, character_id=character.id, position=0, verbatim="ここを通して",
                              vivid="通してと頼んだ", vague="何か頼んだ", source_hash=""))
        s.add(Event(name="市の喧嘩", text="市で喧嘩があった", hidden=False, time="11592/03/15 25:00",
                    location_id=town.id))
        s.commit()
        yield LongDay(calendar=calendar, story_id=story.id, character_id=character.id, episode_id=episode.id)


def test_knowledge_tells_now_and_how_old_things_are_in_the_story_calendar(long_day):
    result = _call("character.read_knowledge.ReadKnowledge",
                   {"episode_id": long_day.episode_id, "character_id": long_day.character_id})

    dumped = json.dumps(result, ensure_ascii=False)
    # 年の数も、暦の始まりの年も渡さない
    assert "1159" not in dumped and "5000" not in dumped
    assert result["いま"] == {"日付": "3月15日", "週": "週の5日目", "時間帯": "深夜", "時刻": "26時ごろ",
                             "暦": "一日は27時間(0〜26時)、一週は7日、一年は12か月・372日(どの月も31日)"}
    me = result["自分"]
    # 33 時間前は、27 時間の一日を一つ越えたので「1日前」。持ち物は今も持っているので「いつから」で言う
    assert me["来歴(古い順)"] == ["2年前から、持ち物: 祖父の短刀", "1日前、門番に呼び止められる"]
    assert me["年齢"] == 22
    assert me["装い"] == [{"物": "外套", "姿": "灰色の外套", "いつから": "1年前"}]
    # 前の話(暦で 1 か月と 5 日前)のセリフは、中身ははっきり覚えている
    assert me["言ったセリフ(古い順)"] == [{"いつ": "1か月前", "覚え": "中身ははっきり覚えている", "セリフ": ["通してと頼んだ"]}]


def test_session_turn_tells_now_and_the_gap_since_the_last_turn(long_day):
    session = SessionStore(long_day.episode_id)
    session.clear()
    session.set_stage({long_day.character_id: "テスト長日の娘"}, [], json.loads(json.dumps(
        {"name": "テスト長日暦", "offset": "5000/01/01 00:00:00", "month_days": [31] * 12, "hours_per_day": 27,
         "days_per_week": 7, "month_names": []})))
    [first] = session.add({"witness_ids": [], "turns": [
        {"character_id": long_day.character_id, "time": "11592/03/15 10:00", "request": "門をくぐる"}]})
    session.answer(first.id, {"action": "くぐる"})
    [second] = session.add({"witness_ids": [], "turns": [
        {"character_id": long_day.character_id, "time": "11592/03/15 25:00", "request": "宿を探す"}]})

    turn = session.turn(long_day.character_id)["record"]

    assert turn["id"] == second.id
    # 25 時は 27 時間の一日の 22 時ごろの割合なので「夜」。暦の長さは knowledge で渡すので、番の行には添えない
    assert turn["いま"] == {"日付": "3月15日", "週": "週の5日目", "時間帯": "夜", "時刻": "25時ごろ"}
    assert turn["前の番から"] == "15時間"
    session.clear()


def test_revert_snapshots_keep_the_western_time_whatever_the_calendar(long_day):
    column = Episode.__table__.columns["start"]
    with using_calendar(long_day.calendar):
        start = Stamp(11592, 3, 15, 26)
        kept = _jsonable(start)
    # 控えは暦に依らない西暦の表記なので、暦の無い文脈で戻しても同じ時刻を指す
    assert kept == start.western_text()
    assert restored_value(column, kept) == start
    with using_calendar(long_day.calendar):
        assert restored_value(column, kept) == start


def test_steps_carry_times_as_western_text(long_day):
    western = Stamp.western(12553, 6, 11, 14).western_text()

    # 作品の暦で読める文脈(web のセッションが運んだ作品)でも、段の入力と結果の時刻は西暦の表記で行き来する
    returned = run_json("character.steps.generation_time", {"location_id": None, "time": western},
                        long_day.story_id)

    assert returned == western


def test_turn_times_are_checked_when_added_and_never_shown_raw(long_day):
    session = SessionStore(long_day.episode_id)
    session.clear()
    session.set_stage({long_day.character_id: "テスト長日の娘"}, [], long_day.calendar.to_json())

    # 暦に無い時(一日 27 時間の 27 時)は、足す前に語り部へ断る
    with pytest.raises(ValueError, match="暦の時刻として読めない"):
        session.add({"witness_ids": [], "turns": [
            {"character_id": long_day.character_id, "time": "11592/03/15 27:00", "request": "夜明けを待つ"}]})
    assert session.load().records == []
    session.clear()
