"""一件ずつの入口へのリクエストを並べて、一つのトランザクションで書くバッチ(`batch.run_batch.RunBatch`)。"""
import pytest

from data_access_logic.batch.form import BatchRequest
from data_access_logic.batch.run_batch import RunBatch
from data_access_logic.character.read_character import ReadCharacter
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.story.form import StoryUpdateForm
from data_access_logic.story.update_story import UpdateStory
from db.guard import ProtectedRowError
from db.schema import Episode, Event, Story, get_env_session
from db.stamp import Stamp
from db.writer import writing


def _request(entrance: str, **args) -> BatchRequest:
    return BatchRequest(entrance=entrance, args=args)


def test_batch_mixes_rows_of_different_parents_in_order(shown, world):
    character_id, other_id = world.character_ids
    dated, undated = shown(ReadCharacter(character_id=character_id))["histories"]
    other_dated = shown(ReadCharacter(character_id=other_id))["histories"][0]

    result = shown(RunBatch(requests=[
        _request("character.update_history.UpdateCharacterHistory", history_id=dated["id"],
                 history={"description": "まとめて直した来歴"}),
        _request("character.delete_history.DeleteCharacterHistory", history_id=undated["id"]),
        _request("character.update_history.UpdateCharacterHistory", history_id=other_dated["id"], history={"kind": "記憶"}),
        _request("character.append_history.AppendCharacterHistory", character_id=character_id,
                 history={"start": "1200", "description": "まとめて足した来歴"}),
    ]))

    assert [row.get("description") for row in result[:2]] == ["まとめて直した来歴", undated["description"]]
    assert result[3]["table"] == "character_history"
    assert [row["description"] for row in shown(ReadCharacter(character_id=character_id))["histories"]] == [
        "まとめて直した来歴", "まとめて足した来歴"]
    assert shown(ReadCharacter(character_id=other_id))["histories"][0]["kind"] == "記憶"


def test_batch_writes_nothing_when_one_request_fails(shown, world):
    dated = shown(ReadCharacter(character_id=world.character_ids[0]))["histories"][0]

    with pytest.raises(UnknownRecordError, match=r"requests\[1\] character.delete_history.DeleteCharacterHistory"):
        RunBatch(requests=[
            _request("character.update_history.UpdateCharacterHistory", history_id=dated["id"],
                     history={"description": "取り消される直し"}),
            _request("character.delete_history.DeleteCharacterHistory", history_id=2_000_000_000),
        ]).run()

    assert shown(ReadCharacter(character_id=world.character_ids[0]))["histories"][0] == dated


def test_batch_rejects_entrances_outside_its_list_and_bad_args(world):
    with pytest.raises(ValueError, match="バッチで呼べない入口"):
        RunBatch(requests=[_request("character.update_character.UpdateCharacter", character={"id": 1})]).run()
    with pytest.raises(ValueError, match=r"requests\[0\]"):
        RunBatch(requests=[_request("character.delete_history.DeleteCharacterHistory", row_id=1)]).run()


def test_batch_keeps_the_writer_guard(shown, world):
    dated = shown(ReadCharacter(character_id=world.character_ids[0]))["histories"][0]
    with pytest.raises(ProtectedRowError, match=r"requests\[0\]"), writing("ai_append"):
        RunBatch(requests=[_request("character.delete_history.DeleteCharacterHistory", history_id=dated["id"])]).run()


def test_batch_updates_episodes_and_events_without_ai(shown, world, mock_ai):
    result = shown(RunBatch(requests=[
        _request("episode.commit_episode.CommitEpisode",
                 episode={"id": world.episode_id, "start": "1200/04/02 12:00:00", "end": "1200/04/02 18:00:00"}),
        _request("event.update_event.UpdateEvent",
                 event={"id": world.event_id, "time": "1200/05/01 12:00:00", "start": "1200/05/01", "end": "1200/05/02"}),
        _request("event.update_event.UpdateEvent", event={"id": world.child_event_id, "parent_event_id": None}),
    ]))

    assert result[0]["start"] == "1200/04/02 12:00:00" and result[1]["start"] == "1200/05/01 00:00:00"
    assert result[2]["parent_event_id"] is None
    with get_env_session() as s:
        assert s.get_one(Episode, world.episode_id).start == Stamp.parse("1200/04/02 12:00:00")
        assert s.get_one(Event, world.child_event_id).parent_event_id is None
    assert not mock_ai.calls


def test_batch_rejects_an_event_cycle(world):
    with pytest.raises(ValueError, match=r"requests\[0\] event.update_event.UpdateEvent"):
        RunBatch(requests=[_request("event.update_event.UpdateEvent",
                                    event={"id": world.event_id, "parent_event_id": world.child_event_id})]).run()


def test_batch_checks_story_parents_after_all_requests(world):
    with get_env_session() as s, s.begin():
        top = Story(name="テスト上の作品", text="", parent_story_id=world.story_id)
        s.add(top)
        s.flush()
        below = Story(name="テスト下の作品", text="", parent_story_id=top.id)
        s.add(below)
        s.flush()
        top_id, below_id = top.id, below.id

    # 一件ずつでは、下の作品を親にした時点で循環に見えて止まる
    with pytest.raises(ValueError, match="子孫の作品の子にはできない"):
        UpdateStory(StoryUpdateForm(id=top_id, parent_story_id=below_id)).run()

    RunBatch(requests=[
        _request("story.update_story.UpdateStory", story={"id": top_id, "parent_story_id": below_id}),
        _request("story.update_story.UpdateStory", story={"id": below_id, "parent_story_id": world.story_id}),
    ]).run()

    with get_env_session() as s:
        assert (s.get_one(Story, top_id).parent_story_id, s.get_one(Story, below_id).parent_story_id) == (
            below_id, world.story_id)
    with pytest.raises(ValueError, match=r"requests\[0\] story.update_story.UpdateStory: .*子孫の作品の子にはできない"):
        RunBatch(requests=[_request("story.update_story.UpdateStory", story={"id": below_id, "parent_story_id": top_id})]).run()
