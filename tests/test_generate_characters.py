import pytest

from data_access_logic.character.generate_characters import GenerateCharacters
from db.schema import Character, CharacterPlace, Location, Story
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


def _place(session, name, with_story=True) -> int:
    place = Location(name=name, kind="村", text="山あいの村", start=Stamp(2000))
    session.add(place)
    session.flush()
    if with_story:
        session.add(Story(name="村の話", place_id=place.id, text="村の筋書き", narration="",
                          state="構想中", start=Stamp(2000), end=Stamp(2300)))
    session.commit()
    return place.id


def test_generates_count_characters_per_place(session):
    place_ids = [_place(session, "村A"), _place(session, "村B")]

    created = GenerateCharacters(
        place_ids, "2100", count=(2, 4), seed=1, ai=MockAIClient(seed=1)).run()

    for place_id in place_ids:
        mine = [item for item in created if item["place_id"] == place_id]
        assert 2 <= len(mine) <= 4
        for item in mine:
            assert session.get(Character, item["id"]).kind == "人物"
            assert session.query(CharacterPlace).filter_by(
                character_id=item["id"], location_id=place_id).count() == 1


def test_stops_before_generating_when_a_place_has_no_story(session):
    place_ids = [_place(session, "村A"), _place(session, "村B", with_story=False)]

    with pytest.raises(ValueError):
        GenerateCharacters(place_ids, "2100", ai=MockAIClient(seed=1)).run()
    assert session.query(Character).count() == 0
