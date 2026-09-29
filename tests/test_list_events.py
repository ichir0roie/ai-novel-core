import pytest

from data_access_logic.event.list_events import ListEvents
from data_access_logic.event.read_events import ReadEvents
from db.schema import Character, Event, EventCharacter, Location
from db.stamp import Stamp


def _event_at(session, place) -> Event:
    record = Event(name="出来事", text="本文", time=Stamp(2100), start=Stamp(2100),
                   end=Stamp(2100, 1, 2), location_id=None if place is None else place.id)
    session.add(record)
    session.commit()
    return record


def test_event_row_has_the_name_of_its_place(session):
    place = Location(name="村", kind="村", text="山あいの村", start=Stamp(2000))
    session.add(place)
    session.commit()
    event = _event_at(session, place)

    (row,) = ListEvents().run()
    (by_place,) = ReadEvents(place_id=place.id).run()

    assert row["id"] == event.id
    assert row["place_name"] == "村"
    assert by_place["place_name"] == "村"


def test_event_row_without_place_has_no_place_name(session):
    _event_at(session, None)

    (row,) = ListEvents().run()

    assert row["place_name"] is None


def test_place_and_character_sharing_an_id_are_not_mixed(session):
    place = Location(name="村", kind="村", text="", start=Stamp(2000))
    other_place = Location(name="町", kind="町", text="", start=Stamp(2000))
    character = Character(name="甲", text="")
    session.add_all([place, other_place, character])
    session.commit()
    assert place.id == character.id
    at_place = _event_at(session, place)
    of_character = _event_at(session, other_place)
    of_character.event_characters = [EventCharacter(character_id=character.id)]
    session.commit()

    assert [row["id"] for row in ReadEvents(place_id=place.id).run()] == [at_place.id]
    assert [row["id"] for row in ReadEvents(character_id=character.id).run()] == [of_character.id]


def test_events_under_an_event(session):
    parent = _event_at(session, None)
    child = Event(name="行動", text="", time=Stamp(2100), parent_event_id=parent.id)
    session.add(child)
    session.commit()

    assert [row["id"] for row in ReadEvents(event_id=parent.id).run()] == [child.id]


def test_read_events_takes_exactly_one_key():
    with pytest.raises(ValueError):
        ReadEvents()
    with pytest.raises(ValueError):
        ReadEvents(place_id=1, character_id=1)
