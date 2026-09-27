import pytest

from ai.claude_code import ai_client
from ai.claude_code.interface._base import UnknownFieldError, UnknownRecordError
from ai.claude_code.interface.randomizer.commit_event import CommitEvent
from ai.claude_code.interface.randomizer.create_random_event import CreateRandomEvent
from ai.claude_code.interface.randomizer.create_random_place import CreateRandomPlace
from ai.claude_code.interface.randomizer.delete_event import DeleteEvent
from ai.claude_code.interface.randomizer.delete_place import DeletePlace
from ai.claude_code.interface.randomizer.update_event import UpdateEvent
from db.schema import (
    Character, ConfirmStatus, Event, EventCharacter, EventIdea, EventSummary, Idea, Location,
)


@pytest.fixture
def place(session):
    location = Location(name="村", kind="村", text="")
    session.add(location)
    session.commit()
    return location.id


@pytest.fixture
def character(session):
    record = Character(name="アル", text="")
    session.add(record)
    session.commit()
    return record.id


def test_create_random_event_is_a_draft_with_overrides():
    draft = CreateRandomEvent(name="祭り", location_id=3).run()
    assert draft["name"] == "祭り"
    assert draft["location_id"] == 3
    assert draft["character_ids"] == []
    assert "id" not in draft


def test_create_random_event_does_not_share_character_ids():
    first = CreateRandomEvent().run()
    first["character_ids"].append(1)
    assert CreateRandomEvent().run()["character_ids"] == []


def test_create_random_place_is_a_draft_with_overrides():
    draft = CreateRandomPlace(name="港町", parent_id=2).run()
    assert draft["name"] == "港町"
    assert draft["parent_id"] == 2
    assert "id" not in draft


def test_commit_event_writes_characters(session, place, character):
    event = CommitEvent({"id": 99, "name": "祭り", "text": "", "time": "2100/01/01 00:00:00",
                         "location_id": place, "character_ids": [character]}).run()
    assert event["id"] != 99
    assert event["name"] == "祭り"
    assert event["character_ids"] == [character]
    assert str(event["time"]) == "2100/01/01 00:00:00"

    links = session.query(EventCharacter).all()
    assert [(link.event_id, link.character_id) for link in links] == [(event["id"], character)]


def test_commit_event_defaults_to_approved(session, place):
    event = CommitEvent({"name": "祭り", "text": "", "time": "2100", "location_id": place}).run()
    assert session.get(Event, event["id"]).confirmed == ConfirmStatus.APPROVED


def test_commit_event_confirmed_can_be_overridden(session, place):
    event = CommitEvent({"name": "祭り", "text": "", "time": "2100", "location_id": place,
                         "confirmed": ConfirmStatus.PENDING}).run()
    assert session.get(Event, event["id"]).confirmed == ConfirmStatus.PENDING


def test_commit_event_summarizes_the_event_right_away(session, place, monkeypatch):
    monkeypatch.setattr(ai_client, "try_generate_json",
                        lambda *a, **k: {"text": "祭りが起きた"})

    event = CommitEvent({"name": "祭り", "text": "本文", "time": "2100",
                         "location_id": place}).run()

    row = session.query(EventSummary).filter_by(event_id=event["id"]).one()
    assert row.text == "祭りが起きた"


def test_commit_event_accepts_json_string(place):
    event = CommitEvent('{"name": "市", "text": "", "time": "2100", "location_id": %d}' % place).run()
    assert event["name"] == "市"
    assert event["character_ids"] == []


@pytest.mark.parametrize("payload", [
    {"time": "2100"},
    {"name": "", "time": "2100"},
    {"name": "時の無い出来事"},
])
def test_commit_event_requires_name_and_time(payload):
    with pytest.raises(ValueError):
        CommitEvent(payload).run()


def test_commit_event_rejects_unknown_field():
    with pytest.raises(UnknownFieldError):
        CommitEvent({"name": "祭り", "time": "2100", "weather": "晴れ"}).run()


@pytest.mark.parametrize("field", ["location_id", "parent_event_id"])
def test_commit_event_rejects_unknown_reference(session, field):
    with pytest.raises(UnknownRecordError):
        CommitEvent({"name": "祭り", "time": "2100", field: 9999}).run()
    assert session.query(Event).count() == 0


def test_commit_event_rejects_unknown_character(session, place, character):
    with pytest.raises(UnknownRecordError):
        CommitEvent({"name": "祭り", "time": "2100", "location_id": place,
                     "character_ids": [character, 9999]}).run()
    assert session.query(Event).count() == 0


def test_delete_place_returns_deleted_row(session, place):
    deleted = DeletePlace(place).run()
    assert deleted == {"id": place, "name": "村", "kind": "村"}
    session.expire_all()
    assert session.get(Location, place) is None


def test_delete_place_refuses_place_with_children(session, place):
    session.add(Location(name="家", kind="建物", text="", parent_id=place))
    session.commit()
    with pytest.raises(ValueError):
        DeletePlace(place).run()
    session.expire_all()
    assert session.get(Location, place) is not None


def test_delete_place_rejects_unknown_id():
    with pytest.raises(UnknownRecordError):
        DeletePlace(9999).run()


def _stored_event(session, place, character) -> int:
    idea = Idea(name="祭りの作法", kind="概念", text="")
    record = Event(name="祭り", text="本文", time="2100", location_id=place)
    session.add_all([idea, record])
    session.flush()
    session.add_all([
        EventCharacter(event_id=record.id, character_id=character),
        EventIdea(event_id=record.id, idea_id=idea.id),
        EventSummary(event_id=record.id, source_hash="x", text="要約"),
    ])
    session.commit()
    return record.id


def test_delete_event_removes_its_links_and_summary(session, place, character):
    event_id = _stored_event(session, place, character)

    deleted = DeleteEvent(event_id).run()

    assert deleted == {"id": event_id, "name": "祭り"}
    session.expire_all()
    assert session.get(Event, event_id) is None
    assert session.query(EventCharacter).count() == 0
    assert session.query(EventIdea).count() == 0
    assert session.query(EventSummary).count() == 0
    assert session.get(Character, character) is not None
    assert session.query(Idea).count() == 1


def test_delete_event_refuses_event_with_children(session, place, character):
    event_id = _stored_event(session, place, character)
    session.add(Event(name="後夜祭", text="", time="2100", parent_event_id=event_id))
    session.commit()

    with pytest.raises(ValueError):
        DeleteEvent(event_id).run()
    session.expire_all()
    assert session.get(Event, event_id) is not None


def test_delete_event_rejects_unknown_id():
    with pytest.raises(UnknownRecordError):
        DeleteEvent(9999).run()


def test_update_event_rewrites_only_the_given_fields_and_summarizes_again(session, place, character, monkeypatch):
    event_id = _stored_event(session, place, character)
    monkeypatch.setattr(ai_client, "try_generate_json", lambda *a, **k: {"text": "灯りの祭り"})

    result = UpdateEvent({"id": event_id, "text": "灯りをともす"}).run()

    assert result["text"] == "灯りをともす"
    assert result["name"] == "祭り"
    session.expire_all()
    assert session.query(EventSummary).filter_by(event_id=event_id).one().text == "灯りの祭り"
    assert session.query(EventCharacter).count() == 1


def test_update_event_requires_a_known_id(session, place, character):
    event_id = _stored_event(session, place, character)
    with pytest.raises(ValueError):
        UpdateEvent({"text": "本文"}).run()
    with pytest.raises(UnknownRecordError):
        UpdateEvent({"id": event_id + 1, "text": "本文"}).run()


@pytest.mark.parametrize("field", ["location_id", "parent_event_id"])
def test_update_event_rejects_unknown_reference(session, place, character, field):
    event_id = _stored_event(session, place, character)
    with pytest.raises(UnknownRecordError):
        UpdateEvent({"id": event_id, field: 9999}).run()


def test_update_event_rejects_itself_as_parent(session, place, character):
    event_id = _stored_event(session, place, character)
    with pytest.raises(ValueError):
        UpdateEvent({"id": event_id, "parent_event_id": event_id}).run()
