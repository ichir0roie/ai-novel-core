import pytest

from ai.claude_code import ai_client, claude_code_time_keeper
from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.time_keeper import frame_generator, episode_summary, episode_generator, main
from db.schema import (
    Character, CharacterRelation, Episode, EpisodeIdea, Event, EventCharacter, Idea, Location, Story,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient

WHEN = Stamp(2100, 5, 1)
KEY = "二人で市場へ行き、甲が古い地図を買う"


class _Writer(MockAIClient):
    """要約は決まった文、本文は決まった題・本文で返す。"""

    def try_generate_json(self, prompt, schema, **kwargs):
        options = {k: kwargs.pop(k) for k in ("model", "effort") if k in kwargs}
        decided = super().try_generate_json(prompt, schema, **kwargs)
        self.calls[-1]["options"] = options
        if schema is episode_summary._SCHEMA:
            return {"summary": "要約した筋", "style": "短い地の文"}
        if schema is episode_generator._SCHEMA:
            return {"title": " 地図の市 ", "viewpoint": "甲", "text": "甲は地図を買った。"}
        return decided


def _writing_call(ai):
    return next(call for call in ai.calls if call["schema"] is episode_generator._SCHEMA)


@pytest.fixture
def place(session):
    record = Location(name="港町", kind="町", text="港町の説明", start=Stamp(2000))
    session.add(record)
    session.commit()
    return record


@pytest.fixture
def story(session, place):
    record = Story(name="港町の話", place_id=place.id, text="港町の筋書き", narration="三人称",
                   state="執筆中", start=Stamp(2100), end=Stamp(2300))
    session.add(record)
    session.commit()
    return record


def _character(session, name, *, start=Stamp(2080)) -> Character:
    record = Character(name=name, text=f"{name}の説明", start=start)
    session.add(record)
    session.commit()
    return record


def _episode(session, story, number, *, start=None) -> Episode:
    record = Episode(story_id=story.id, start=start or Stamp(2100, 4, number), title=f"第{number}話",
                     synced=True, text=f"{number}話の本文")
    session.add(record)
    session.commit()
    return record


def _event(session, place, characters, start, name) -> Event:
    record = Event(name=name, text=f"{name}の本文", time=start, start=start, end=start,
                   location_id=place.id if place else None)
    record.event_characters = [EventCharacter(character_id=c.id) for c in characters]
    session.add(record)
    session.commit()
    return record


def test_episode_is_added_to_the_story_with_the_given_key_and_time(session, story):
    first = _character(session, "甲")
    ai = _Writer(seed=1)

    record = frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id])

    assert record.story_id == story.id
    assert record.key == KEY and record.start == WHEN
    assert record.title == "地図の市"
    assert record.text == "甲は地図を買った。" and record.letters == len(record.text)
    assert record.synced is True
    assert record.viewpoint == "甲"
    assert record.place is None


def test_prompt_carries_the_story_key_characters_and_their_ages(session, story):
    first = _character(session, "甲", start=Stamp(2085, 6, 1))
    second = _character(session, "乙")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, "2100/05/01", [first.id, second.id])

    call = _writing_call(ai)
    assert call["system"] == episode_generator._SYSTEM_PROMPT
    assert style.style_instruction("episode") in call["system"] and EVENT_AGE_INSTRUCTION in call["system"]
    prompt = call["prompt"]
    assert "港町の筋書き" in prompt
    assert "港町の説明" in prompt
    assert f"この話の種(これを場面まで展開する。種に無い出来事を足さない): {KEY}" in prompt
    assert '"name": "甲"' in prompt and '"age": 14' in prompt
    assert '"name": "乙"' in prompt
    assert "5000〜8000字" in prompt


def test_style_extras_from_the_caller_reach_the_system_prompt(session, story):
    """世界の舞台設定・既存の話から抽出した文体の癖は、コアに定数で持たず、呼び出し側から渡す。"""
    first = _character(session, "甲")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id],
                             shared_style_extra="西暦一万年のSF世界", style_extra="この世界の文体の癖")

    system = _writing_call(ai)["system"]
    assert "西暦一万年のSF世界" in system and "この世界の文体の癖" in system
    assert system != episode_generator._SYSTEM_PROMPT


def test_unknown_characters_are_left_out_of_the_prompt(session, story):
    first = _character(session, "甲")
    _character(session, "丙")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id])

    assert '"name": "丙"' not in _writing_call(ai)["prompt"]


def test_previous_episodes_are_given_as_summaries(session, story):
    episodes = [_episode(session, story, number) for number in range(1, 5)]
    first = _character(session, "甲")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id],
                             [episodes[3].id, episodes[1].id, episodes[2].id])

    prompt = _writing_call(ai)["prompt"]
    assert "話の本文" not in prompt
    assert prompt.count('"summary": "要約した筋"') == 3
    assert prompt.index('"title": "第2話"') < prompt.index('"title": "第3話"') < prompt.index('"title": "第4話"')
    assert '"title": "第1話"' not in prompt
    assert "直前の話の文体(これに揃える): 短い地の文" in prompt


def test_previous_episodes_default_to_the_last_three_before_the_time(session, story):
    for number in range(1, 5):
        _episode(session, story, number)
    _episode(session, story, 9, start=Stamp(2100, 6, 1))
    first = _character(session, "甲")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id])

    prompt = _writing_call(ai)["prompt"]
    for number in (2, 3, 4):
        assert f'"title": "第{number}話"' in prompt
    assert '"title": "第1話"' not in prompt and '"title": "第9話"' not in prompt


def test_first_episode_has_no_previous_ones(session, story):
    first = _character(session, "甲")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id])

    assert "直前の話(古い順): (無し)" in _writing_call(ai)["prompt"]
    assert not any(call["schema"] is episode_summary._SCHEMA for call in ai.calls)


def test_characters_recent_and_later_events_are_told_without_their_texts(session, story, place):
    first = _character(session, "甲")
    second = _character(session, "乙")
    elsewhere = Location(name="山村", kind="村", text="")
    session.add(elsewhere)
    session.commit()
    _event(session, elsewhere, [first], Stamp(2100, 3, 1), "甲の前の出来事")
    _event(session, elsewhere, [second], Stamp(2100, 7, 1), "乙の後の出来事")
    _event(session, place, [], Stamp(2100, 4, 1), "港町の前の出来事")
    _event(session, elsewhere, [], Stamp(2100, 4, 2), "よその出来事")
    session.add(CharacterRelation(character_id_1=first.id, character_id_2=second.id, relation="幼なじみ",
                                  text="", start=Stamp(2090)))
    session.commit()
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id, second.id])

    prompt = _writing_call(ai)["prompt"]
    assert '"name": "甲の前の出来事"' in prompt and '"place": "山村"' in prompt
    assert "甲から見た乙: 幼なじみ" in prompt
    later = next(line for line in prompt.splitlines() if line.startswith("この時点より後に既に決まっている出来事"))
    assert '"name": "乙の後の出来事"' in later
    here = next(line for line in prompt.splitlines() if line.startswith("この場所の直近の出来事"))
    assert '"name": "港町の前の出来事"' in here
    assert "よその出来事" not in prompt
    assert "の出来事の本文" not in prompt


def test_given_place_and_viewpoint_are_kept_on_the_episode(session, story):
    first = _character(session, "甲")
    second = _character(session, "乙")
    market = Location(name="魚市場", kind="市場", text="魚市場の説明")
    session.add(market)
    session.commit()
    ai = _Writer(seed=1)

    record = frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id, second.id],
                                      place_id=market.id, viewpoint="乙")

    assert record.place == "魚市場" and record.viewpoint == "乙"
    prompt = _writing_call(ai)["prompt"]
    assert "魚市場の説明" in prompt and "港町の説明" not in prompt
    assert "視点: 乙" in prompt


def test_ideas_the_key_hits_are_linked_to_the_episode(session, story, place, monkeypatch):
    first = _character(session, "甲")
    idea = Idea(name="古い地図", kind="物", text="古い地図の説明", start=Stamp(2000), location_id=place.id)
    session.add(idea)
    session.commit()
    monkeypatch.setattr(episode_generator.idea_context.idea_search, "keywords_of",
                        lambda *a, **k: [{"keyword": "古い地図", "variants": [], "coined": False,
                                          "kind": "物", "description": "", "start": None, "end": None}])
    ai = _Writer(seed=1)

    record = frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id])

    assert "古い地図の説明" in _writing_call(ai)["prompt"]
    assert [row.idea_id for row in session.query(EpisodeIdea).filter_by(episode_id=record.id)] == [idea.id]


class _NoText(_Writer):
    def try_generate_json(self, prompt, schema, **kwargs):
        decided = super().try_generate_json(prompt, schema, **kwargs)
        return {} if schema is episode_generator._SCHEMA else decided


def test_no_episode_is_added_without_a_text(session, story):
    first = _character(session, "甲")

    assert frame_generator.generate(session, _NoText(seed=1), story.id, KEY, WHEN, [first.id]) is None
    assert session.query(Episode).count() == 0


def test_bad_arguments_are_refused(session, story):
    first = _character(session, "甲")
    ai = _Writer(seed=1)

    with pytest.raises(ValueError):
        frame_generator.generate(session, ai, story.id, "  ", WHEN, [first.id])
    with pytest.raises(ValueError):
        frame_generator.generate(session, ai, story.id, KEY, WHEN, [])
    with pytest.raises(ValueError):
        frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id + 100])
    with pytest.raises(ValueError):
        frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id], [12345])
    with pytest.raises(ValueError):
        frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id], place_id=12345)
    with pytest.raises(LookupError):
        frame_generator.generate(session, ai, story.id + 100, KEY, WHEN, [first.id])
    assert session.query(Episode).count() == 0


def test_main_write_episode_returns_the_id(session, story):
    first = _character(session, "甲")

    episode_id = main.write_episode(_Writer(seed=1), story.id, KEY, "2100/05/01", [first.id])

    record = session.get(Episode, episode_id)
    assert record.start == WHEN and record.key == KEY


def test_claude_writes_only_the_text_with_the_episode_model(session, story, monkeypatch):
    first = _character(session, "甲")
    _episode(session, story, 1)
    ai = _Writer(seed=1)
    monkeypatch.setattr(claude_code_time_keeper, "ai_client", ai)

    claude_code_time_keeper.claude_write_episode_main(story.id, KEY, WHEN, [first.id])

    assert _writing_call(ai)["options"] == {"model": "claude-fable-5-1", "effort": "high"}
    assert all(call["options"] == {} for call in ai.calls if call["schema"] is not episode_generator._SCHEMA)


def _slot(session, story, *, title="枠の題", start=WHEN, key="", viewpoint="甲(十四歳)", place=None) -> Episode:
    record = Episode(story_id=story.id, title=title, start=start, key=key,
                     synced=False, viewpoint=viewpoint, place=place)
    session.add(record)
    session.commit()
    return record


def test_given_slot_is_filled_instead_of_adding_an_episode(session, story):
    first = _character(session, "甲")
    slot = _slot(session, story, place="波止場")
    ai = _Writer(seed=1)

    record = frame_generator.generate(session, ai, story.id, KEY, None, [first.id], episode_id=slot.id)

    assert record.id == slot.id and session.query(Episode).count() == 1
    assert record.title == "枠の題" and record.start == WHEN and record.key == KEY
    assert record.text == "甲は地図を買った。" and record.letters == len(record.text)
    assert record.synced is True
    assert record.viewpoint == "甲(十四歳)" and record.place == "波止場"
    assert "視点: 甲(十四歳)" in _writing_call(ai)["prompt"]


def test_slot_key_is_used_when_no_key_is_given_and_ai_title_fills_an_empty_one(session, story):
    first = _character(session, "甲")
    slot = _slot(session, story, title="", key=KEY)

    record = frame_generator.generate(session, _Writer(seed=1), story.id, None, None, [first.id],
                                      episode_id=slot.id)

    assert record.key == KEY and record.title == "地図の市"


def test_slot_is_not_given_as_its_own_previous_episode(session, story):
    first = _character(session, "甲")
    before = _episode(session, story, 1)
    slot = _slot(session, story, title="枠の題")
    ai = _Writer(seed=1)

    frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id], [before.id, slot.id],
                             episode_id=slot.id)

    prompt = _writing_call(ai)["prompt"]
    assert '"title": "第1話"' in prompt and '"title": "枠の題"' not in prompt


def test_slot_is_left_untouched_without_a_text(session, story):
    first = _character(session, "甲")
    slot = _slot(session, story)

    assert frame_generator.generate(session, _NoText(seed=1), story.id, KEY, None, [first.id],
                                    episode_id=slot.id) is None
    session.refresh(slot)
    assert slot.text == "" and slot.key == "" and slot.synced is False
    # 枠(slot)自身の一行だけで、本文を書いた行は増えない
    assert session.query(Episode).count() == 1


def test_bad_slots_are_refused(session, story):
    first = _character(session, "甲")
    other = Story(name="別の話", text="", narration="三人称", state="執筆中")
    session.add(other)
    session.commit()
    written = _episode(session, story, 1)
    elsewhere = _slot(session, other)
    ai = _Writer(seed=1)

    for episode_id in (12345, written.id, elsewhere.id):
        with pytest.raises(ValueError):
            frame_generator.generate(session, ai, story.id, KEY, WHEN, [first.id], episode_id=episode_id)
    assert session.get(Episode, written.id).text == "1話の本文"


def test_claude_write_episode_main_fills_the_slot(session, story, monkeypatch):
    first = _character(session, "甲")
    slot = _slot(session, story)
    monkeypatch.setattr(claude_code_time_keeper, "ai_client", _Writer(seed=1))

    assert claude_code_time_keeper.claude_write_episode_main(
        story.id, KEY, None, [first.id], episode_id=slot.id) == slot.id


def test_claude_write_episode_main_takes_the_model_of_the_text(session, story, monkeypatch):
    first = _character(session, "甲")
    ai = _Writer(seed=1)
    monkeypatch.setattr(claude_code_time_keeper, "ai_client", ai)

    episode_id = claude_code_time_keeper.claude_write_episode_main(
        story.id, KEY, WHEN, [first.id], model="claude-sonnet-5", effort="medium")

    assert _writing_call(ai)["options"] == {"model": "claude-sonnet-5", "effort": "medium"}
    text = session.get(Episode, episode_id)
    assert (text.model, text.effort) == ("claude-sonnet-5", "medium")


def test_other_generations_default_to_sonnet_medium():
    assert (ai_client._MODEL, ai_client._EFFORT) == ("claude-sonnet-5", "medium")
    assert (ai_client.EPISODE_MODEL, ai_client.EPISODE_EFFORT) == ("claude-fable-5-1", "high")


def test_text_is_written_separately_into_the_frame(session, story):
    first = _character(session, "甲")
    before = _episode(session, story, 1)
    slot = _slot(session, story, title="", key=KEY, place="波止場")
    ai = _Writer(seed=1)

    text = episode_generator.generate(session, ai, slot.id, [first.id], writer_options={"model": "m", "effort": "e"})

    session.refresh(slot)
    assert text.id == slot.id
    assert (text.text, text.letters, text.model, text.effort) == ("甲は地図を買った。", 9, "m", "e")
    assert slot.title == "地図の市" and slot.viewpoint == "甲(十四歳)" and slot.place == "波止場"
    assert slot.synced is True and session.query(Episode).count() == 2
    prompt = _writing_call(ai)["prompt"]
    assert f"この話の種(これを場面まで展開する。種に無い出来事を足さない): {KEY}" in prompt
    assert '"title": "第1話"' in prompt and before.id != slot.id


def test_text_needs_a_frame_with_key_and_time(session, story):
    first = _character(session, "甲")
    no_key = _slot(session, story, key="")
    no_time = _slot(session, story, key=KEY, start=None)
    written = _episode(session, story, 1)
    ai = _Writer(seed=1)

    for episode_id in (12345, no_key.id, no_time.id, written.id):
        with pytest.raises(ValueError):
            episode_generator.generate(session, ai, episode_id, [first.id])
    with pytest.raises(ValueError):
        episode_generator.generate(session, ai, _slot(session, story, key=KEY).id, [])
    # まだ本文が付いたのは最初に足した「written」だけ
    assert session.query(Episode).filter(Episode.text != "").count() == 1


def test_frame_is_left_without_a_text(session, story):
    first = _character(session, "甲")
    slot = _slot(session, story, key=KEY)

    assert episode_generator.generate(session, _NoText(seed=1), slot.id, [first.id]) is None
    session.refresh(slot)
    assert slot.text == "" and slot.synced is False
    assert session.query(Episode).filter(Episode.text != "").count() == 0


def test_claude_fill_episode_main_writes_with_fable_high(session, story, monkeypatch):
    first = _character(session, "甲")
    slot = _slot(session, story, key=KEY)
    ai = _Writer(seed=1)
    monkeypatch.setattr(claude_code_time_keeper, "ai_client", ai)

    episode_id = claude_code_time_keeper.claude_fill_episode_main(slot.id, [first.id])

    session.refresh(slot)
    text = session.get(Episode, episode_id)
    assert text.id == slot.id and (text.model, text.effort) == ("claude-fable-5-1", "high")
    assert all(call["options"] == {} for call in ai.calls if call["schema"] is not episode_generator._SCHEMA)
