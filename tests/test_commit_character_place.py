import pytest

from data_access_logic.character.commit_character_place import CommitCharacterPlace
from data_access_logic.entrypoint import UnknownRecordError
from db.schema import Character, CharacterPlace, Location
from db.stamp import Stamp


@pytest.fixture
def world(session):
    village = Location(name="村", kind="村", text="", start=Stamp(2100), end=Stamp(2200))
    person = Character(name="人", kind="人物", text="")
    session.add_all([village, person])
    session.commit()
    return {"village": village.id, "person": person.id}


def test_commit_adds_place_for_existing_character(session, world):
    result = CommitCharacterPlace({
        "character_id": world["person"], "location_id": world["village"], "start": "2120"}).run()

    row = session.get(CharacterPlace, result["id"])
    assert row.character_id == world["person"] and row.location_id == world["village"]
    assert row.start == Stamp(2120) and result["start"] == "2120/01/01 00:00:00"


def test_commit_rejects_span_outside_place(session, world):
    with pytest.raises(ValueError, match="end=2200/01/01 00:00:00 以後"):
        CommitCharacterPlace({
            "character_id": world["person"], "location_id": world["village"], "start": "2300"}).run()
    assert session.query(CharacterPlace).count() == 0


def test_commit_rejects_unknown_or_missing_references(session, world):
    with pytest.raises(ValueError, match="character_id は必須"):
        CommitCharacterPlace({"location_id": world["village"]}).run()
    with pytest.raises(UnknownRecordError, match="character_id=999"):
        CommitCharacterPlace({"character_id": 999, "location_id": world["village"]}).run()
    with pytest.raises(UnknownRecordError, match="location_id=999"):
        CommitCharacterPlace({"character_id": world["person"], "location_id": 999}).run()
    assert session.query(CharacterPlace).count() == 0


def test_update_sets_end_when_moving(session, world):
    from data_access_logic.character.update_character_place import UpdateCharacterPlace

    row = CommitCharacterPlace({
        "character_id": world["person"], "location_id": world["village"], "start": "2120"}).run()
    updated = UpdateCharacterPlace({"id": row["id"], "end": "2130"}).run()
    assert updated["end"] == "2130/01/01 00:00:00"
    session.expire_all()
    assert session.get(CharacterPlace, row["id"]).end == Stamp(2130)

    with pytest.raises(ValueError, match="id は必須"):
        UpdateCharacterPlace({"end": "2130"}).run()
    with pytest.raises(UnknownRecordError, match="location_id=999"):
        UpdateCharacterPlace({"id": row["id"], "location_id": 999}).run()
