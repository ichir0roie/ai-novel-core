from ai.time_keeper import event_progression_generator
from ai.time_keeper.random_character_generator import _generate_one
from data_access_logic.query.base import character_active_condition
from db.schema import Character, CharacterPlace, Location, Story
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


def _place(session) -> Location:
    place = Location(name="村", kind="村", text="", start=Stamp(2000), active_random_generation=True)
    session.add(place)
    session.flush()
    session.add(Story(name="村の話", place_id=place.id, text="村の筋書き", narration="", state="構想中",
                      start=Stamp(2000), end=Stamp(2300)))
    session.commit()
    return place


def _character(session, place, *, main_character: bool) -> Character:
    record = Character(name="仮名", text="", main_character=main_character, start=Stamp(2000))
    session.add(record)
    session.flush()
    session.add(CharacterPlace(character_id=record.id, location_id=place.id, start=Stamp(2000)))
    session.commit()
    return record


def test_character_active_condition_matches_main_character_flag(session):
    place = _place(session)
    main_character = _character(session, place, main_character=True)
    sub_character = _character(session, place, main_character=False)

    ids = {row for row, in session.query(Character.id).filter(character_active_condition()).all()}
    assert ids == {sub_character.id}
    assert main_character.id not in ids


def test_group_by_place_keeps_only_sub_characters(session):
    place = _place(session)
    main_character = _character(session, place, main_character=True)
    sub_character = _character(session, place, main_character=False)

    grouped = event_progression_generator._group_by_place(session, Stamp(2100))

    ids = {c.id for c in grouped[place.id]}
    assert sub_character.id in ids
    assert main_character.id not in ids


def test_generated_character_is_marked_sub_character(session):
    place = _place(session)
    ai = MockAIClient(seed=1)

    record = _generate_one(session, place, Stamp(2100, 1, 1), __import__("random").Random(1), ai, person=True)

    assert record.main_character is False


def test_character_without_the_flag_is_a_sub_character(session):
    record = Character(name="仮名", text="", start=Stamp(2000))
    session.add(record)
    session.commit()

    assert record.main_character is False
