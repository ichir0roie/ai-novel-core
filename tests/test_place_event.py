import random
import re

import pytest

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION, EVENT_NOVEL_INSTRUCTION
from ai.time_keeper import event_progression_generator, main, place_event_generator
from db.schema import (
    Character, CharacterPlace, ConfirmStatus, Event, EventCharacter, EventSeed, Location, Story,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient

WHEN = Stamp(2100, 5, 1)
KEY = "市場の喧嘩"


class _InvolvesEveryone(MockAIClient):
    def try_generate_json(self, prompt, schema, **kwargs):
        decided = super().try_generate_json(prompt, schema, **kwargs)
        if schema is event_progression_generator._PLACE_SCHEMA:
            decided["character_ids"] = sorted({int(i) for i in re.findall(r"'character_id': (\d+)", prompt)})
            decided["character_moves"] = []
        return decided


def _place(session, name="港町", *, active=True) -> Location:
    place = Location(name=name, kind="町", text=f"{name}の説明", start=Stamp(2000),
                     active_random_generation=active)
    session.add(place)
    session.flush()
    session.add(Story(name=f"{name}の話", place_id=place.id, text=f"{name}の筋書き", narration="",
                      state="構想中", start=Stamp(2090), end=Stamp(2300)))
    session.commit()
    return place


def _character(session, place, name, *, main_character=False, start=Stamp(2080), end=None) -> Character:
    record = Character(name=name, text=f"{name}の説明", main_character=main_character, start=start, end=end)
    session.add(record)
    session.flush()
    if place is not None:
        session.add(CharacterPlace(character_id=record.id, location_id=place.id, start=start))
    session.commit()
    return record


def _event(session, place, characters, start, end, name) -> Event:
    record = Event(name=name, text=f"{name}の本文", time=start, start=start, end=end, location_id=place.id)
    record.event_characters = [EventCharacter(character_id=c.id) for c in characters]
    session.add(record)
    session.commit()
    return record


def _involved(session, event) -> set[int]:
    return {row.character_id for row in session.query(EventCharacter).filter_by(event_id=event.id)}


def _call(ai, schema):
    return next(call for call in ai.calls if call["schema"] is schema)


def test_event_happens_at_the_given_place_and_time_among_those_there(session):
    place = _place(session)
    elsewhere = _place(session, "山村")
    first = _character(session, place, "甲")
    second = _character(session, place, "乙")
    _character(session, elsewhere, "よその者")
    _character(session, place, "主役格", main_character=True)
    _character(session, place, "故人", end=Stamp(2090))
    _character(session, place, "まだ生まれない者", start=Stamp(2110))
    ai = _InvolvesEveryone(seed=1)

    record = place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1))

    assert record.start == WHEN and record.time == WHEN
    assert record.location_id == place.id
    assert _involved(session, record) == {first.id, second.id}
    prompts = "".join(call["prompt"] for call in ai.calls)
    for name in ("よその者", "主役格", "故人", "まだ生まれない者"):
        assert f"'name': '{name}'" not in prompts


def test_generated_place_event_is_unconfirmed(session):
    place = _place(session)
    _character(session, place, "甲")
    ai = _InvolvesEveryone(seed=1)

    record = place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1))

    assert record.confirmed == ConfirmStatus.PENDING


def test_those_in_another_event_then_are_left_out(session):
    place = _place(session)
    free = _character(session, place, "甲")
    busy = _character(session, place, "乙")
    _event(session, place, [busy], Stamp(2100, 4, 20), Stamp(2100, 5, 10), "旅の途中")
    ai = _InvolvesEveryone(seed=1)

    record = place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1))

    assert _involved(session, record) == {free.id}


def test_a_place_left_out_of_random_generation_can_still_be_named(session):
    place = _place(session, active=False)
    character = _character(session, place, "甲")

    record = place_event_generator.generate_at(
        session, _InvolvesEveryone(seed=1), place.id, WHEN, KEY, random.Random(1))

    assert _involved(session, record) == {character.id}


def test_returns_none_when_no_one_is_there(session):
    place = _place(session)
    _character(session, place, "主役格", main_character=True)

    assert place_event_generator.generate_at(session, MockAIClient(seed=1), place.id, WHEN, KEY) is None
    assert session.query(Event).count() == 0


def test_an_empty_key_or_an_unknown_place_is_refused(session):
    place = _place(session)
    _character(session, place, "甲")

    with pytest.raises(ValueError):
        place_event_generator.generate_at(session, MockAIClient(seed=1), place.id, WHEN, "  ")
    with pytest.raises(ValueError):
        place_event_generator.generate_at(session, MockAIClient(seed=1), place.id + 100, WHEN, KEY)


def test_the_key_is_told_to_every_step(session):
    place = _place(session)
    _character(session, place, "甲")
    ai = MockAIClient(seed=1)

    place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1))

    for schema in (
        event_progression_generator._JUDGEMENT_SCHEMA,
        event_progression_generator._CANDIDATE_SCHEMA,
        event_progression_generator._PLACE_SCHEMA,
    ):
        assert place_event_generator._note(KEY) in _call(ai, schema)["prompt"]
    novel = ai.calls[-1]
    assert novel["schema"] is place_event_generator._NOVEL_SCHEMA
    assert f"場面の指定: {KEY}" in novel["prompt"]


def test_the_story_is_not_told(session):
    place = _place(session)
    _character(session, place, "甲")
    ai = MockAIClient(seed=1)

    place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1))

    prompts = "\n".join(call["prompt"] for call in ai.calls)
    assert "港町の筋書き" not in prompts
    assert "進めたい筋書き" not in prompts


def test_novel_is_told_each_ones_previous_event_and_the_later_ones(session):
    place = _place(session)
    first = _character(session, place, "甲")
    second = _character(session, place, "乙")
    _event(session, place, [first], Stamp(2100, 3, 1), Stamp(2100, 3, 2), "甲の前の出来事")
    _event(session, place, [second], Stamp(2100, 6, 1), Stamp(2100, 6, 2), "乙の後の出来事")
    ai = _InvolvesEveryone(seed=1)

    record = place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1))

    novel = ai.calls[-1]
    assert novel["system"] == place_event_generator._NOVEL_SYSTEM_PROMPT
    assert EVENT_NOVEL_INSTRUCTION in novel["system"] and EVENT_AGE_INSTRUCTION in novel["system"]
    assert '"甲": {"name": "甲の前の出来事"' in novel["prompt"]
    assert '"乙": "(無し)"' in novel["prompt"]
    assert "甲の前の出来事の本文" not in novel["prompt"]
    later = next(line for line in novel["prompt"].splitlines()
                 if line.startswith("この時点より後に既に決まっている出来事"))
    assert '"name": "乙の後の出来事"' in later
    assert "1700〜2700字の小説" in novel["prompt"]
    assert record.text == f"モックtext{len(ai.calls)}"


def test_style_extras_from_the_caller_reach_the_novel_system_prompt(session):
    """世界の舞台設定・既存の話から抽出した文体の癖は、コアに定数で持たず、呼び出し側から渡す。"""
    place = _place(session)
    _character(session, place, "甲")
    ai = MockAIClient(seed=1)

    place_event_generator.generate_at(session, ai, place.id, WHEN, KEY, random.Random(1),
                                      shared_style_extra="西暦一万年のSF世界", style_extra="この世界の文体の癖")

    novel = ai.calls[-1]
    assert "西暦一万年のSF世界" in novel["system"] and "この世界の文体の癖" in novel["system"]
    assert novel["system"] != place_event_generator._NOVEL_SYSTEM_PROMPT


def test_place_event_takes_the_time_as_text_and_returns_the_id(session):
    place = _place(session)
    character = _character(session, place, "甲")

    event_id = main.place_event(_InvolvesEveryone(seed=1), place.id, "2100/05/01", KEY)

    record = session.get(Event, event_id)
    assert record.start == WHEN
    assert _involved(session, record) == {character.id}
    # 毎日のルーチンと同じく、先に作品の筋書きから種を抜き出している
    assert session.query(EventSeed).count() > 0
