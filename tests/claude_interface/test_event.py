"""claude が CLI から `show()` で呼ぶ、出来事(`data_access_logic/event/`・`event_seed/`)の入口。"""
from data_access_logic.event.commit_event import CommitEvent
from data_access_logic.event.create_random_event import CreateRandomEvent
from data_access_logic.event.delete_event import DeleteEvent
from data_access_logic.event.form import EventCreateForm, EventForm, EventUpdateForm
from data_access_logic.event.generate_event import GenerateEvent
from data_access_logic.event.list_events import ListEvents
from data_access_logic.event.read_events import ReadEvents
from data_access_logic.event.update_event import UpdateEvent
from data_access_logic.event_seed.form import EventSeedUpdateForm
from data_access_logic.event_seed.update_event_seed import UpdateEventSeed
from db.schema import ConfirmStatus


def test_commit_event(shown, world, mock_ai):
    result = shown(CommitEvent(EventCreateForm(
        name="テスト祭", time="1200/05/01 10:00:00", text="祭が開かれた", hidden=True,
        confirmed=ConfirmStatus.PENDING, parent_event_id=world.event_id, location_id=world.place_id,
        start="1200/05/01", end="1200/05/03", event_seeded=True, meme_seeded=True,
        character_ids=world.character_ids)))

    assert (result["name"], result["text"]) == ("テスト祭", "祭が開かれた")
    assert result["time"] == "1200/05/01 10:00:00"
    assert (result["hidden"], result["confirmed"]) == (True, "未確認")
    assert (result["parent_event_id"], result["location_id"]) == (world.event_id, world.place_id)
    assert (result["start"], result["end"]) == ("1200/05/01 00:00:00", "1200/05/03 00:00:00")
    assert (result["event_seeded"], result["meme_seeded"]) == (True, True)
    assert result["character_ids"] == world.character_ids
    assert mock_ai.calls


def test_create_random_event(shown):
    result = shown(CreateRandomEvent(name="乱数の出来事", text="乱数で作った出来事", hidden=True))

    assert (result["name"], result["text"], result["hidden"]) == ("乱数の出来事", "乱数で作った出来事", True)
    EventForm.model_validate(result)


def test_delete_event(shown, world):
    result = shown(DeleteEvent(event_id=world.child_event_id))

    assert result == {"id": world.child_event_id, "name": "テスト取引"}


def test_generate_event(shown, world, mock_ai):
    result = shown(GenerateEvent(
        event=EventForm(
            name="生成の出来事", text="市で揉め事が起きる", time="1200/04/05 09:00:00", start="1200/04/05",
            end="1200/04/06", location_id=world.place_id, character_ids=world.character_ids, hidden=True,
            parent_event_id=world.event_id),
        seed=3, shared_style_extra="共有の文体の好み", style_extra="出来事の文体の好み"))

    assert result["location_id"] == world.place_id
    assert result["time"] == "1200/04/05 09:00:00"
    assert (result["hidden"], result["parent_event_id"]) == (True, world.event_id)
    assert result["end"] == "1200/04/06 00:00:00"
    assert set(result["character_ids"]) <= set(world.character_ids)
    assert mock_ai.calls


def test_list_events(shown, world):
    result = shown(ListEvents())

    assert {world.event_id, world.child_event_id} <= {event["id"] for event in result}


def test_read_events(shown, world):
    result = shown(ReadEvents(character_id=world.character_ids[0], limit=5, until="1200/12/31"))

    assert world.event_id in [event["id"] for event in result]


def test_update_event(shown, world, mock_ai):
    result = shown(UpdateEvent(EventUpdateForm(
        id=world.child_event_id, name="テスト大取引", time="1200/04/01 16:00:00", text="大きな取引がまとまった",
        hidden=True, confirmed=ConfirmStatus.REJECTED, parent_event_id=world.event_id, location_id=world.neighbor_id,
        start="1200/04/01 16:00:00", end="1200/04/01 17:00:00", event_seeded=False, meme_seeded=False,
        character_ids=[world.character_ids[1]])))

    assert (result["name"], result["text"]) == ("テスト大取引", "大きな取引がまとまった")
    assert result["time"] == "1200/04/01 16:00:00"
    assert (result["hidden"], result["confirmed"]) == (True, "非承認")
    assert (result["parent_event_id"], result["location_id"]) == (world.event_id, world.neighbor_id)
    assert (result["start"], result["end"]) == ("1200/04/01 16:00:00", "1200/04/01 17:00:00")
    assert result["character_ids"] == [world.character_ids[1]]
    assert mock_ai.calls


def test_update_event_seed(shown, world):
    result = shown(UpdateEventSeed(EventSeedUpdateForm(id=world.event_seed_id, text="直した種", consolidated=True)))

    assert result == {"id": world.event_seed_id, "text": "直した種", "consolidated": True}
