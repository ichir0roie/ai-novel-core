import random

import pytest

from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.randomizer.update_event_seed import UpdateEventSeed
from ai.time_keeper import event_seed
from data_access_logic.query import event_seed_query
from db.schema import Character, Plot, Episode, Event, EventSeed, Story
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


class _Fails(MockAIClient):
    def try_generate_json(self, prompt, schema, **kwargs):
        super().try_generate_json(prompt, schema, **kwargs)
        return {}


class _NoSeeds(MockAIClient):
    def try_generate_json(self, prompt, schema, **kwargs):
        super().try_generate_json(prompt, schema, **kwargs)
        return {"seeds": []}


def _story(session, text="村の筋書き") -> Story:
    story = Story(name="村の話", text=text, narration="", state="構想中")
    session.add(story)
    session.commit()
    return story


def test_seeds_are_drawn_out_of_stories_plots_character_plots_and_events(session):
    story = _story(session)
    with_key = Plot(story_id=story.id, title="一", key="種一", synced=False,
                       episode=Episode(text="本文一"))
    text_only = Plot(story_id=story.id, title="二", key="", synced=False, episode=Episode(text="本文二"))
    empty = Plot(story_id=story.id, title="三", key="", synced=False)
    planned = Character(name="甲", text="説明\n\n# plot\n\n起: 旅に出る\n\n# 来歴\n\n村の生まれ")
    unplanned = Character(name="乙", text="説明だけ")
    happened = Event(name="峠越え", text="峠を越えた", time=Stamp(2100))
    session.add_all([with_key, text_only, empty, planned, unplanned, happened])
    session.commit()
    ai = MockAIClient(seed=1)

    added = event_seed.refresh(session, ai)

    assert added == session.query(EventSeed).count() == 2
    assert all(record.event_seeded for record in (story, with_key, text_only, planned, happened))
    # 本文が無い元は、書かれるまで印を立てない
    assert not empty.event_seeded and not unplanned.event_seeded
    prompt = ai.calls[0]["prompt"]
    assert "種一" in prompt and "本文一" not in prompt and "本文二" in prompt
    assert "起: 旅に出る" in prompt and "村の生まれ" not in prompt
    assert "## 元5(event)\n峠を越えた" in prompt
    assert ai.calls[0]["system"] == event_seed._SYSTEM_PROMPT


def test_unseeded_records_are_the_ones_not_flagged(session):
    seeded = _story(session, "一つ目")
    unseeded = _story(session, "二つ目")
    seeded.event_seeded = True
    session.commit()

    rows = session.scalars(event_seed_query.unseeded_select(Story)).all()

    assert [row.id for row in rows] == [unseeded.id]


def test_a_source_is_drawn_only_once_even_without_seeds_or_after_edits(session):
    story = _story(session)
    event_seed.refresh(session, _NoSeeds(seed=1))
    story.text = "書き直した筋書き"
    session.commit()
    ai = MockAIClient(seed=1)

    assert event_seed.refresh(session, ai) == 0
    assert ai.calls == []


def test_clearing_the_flag_draws_the_source_again(session):
    story = _story(session)
    event_seed.refresh(session, MockAIClient(seed=1))
    story.text = "書き直した筋書き"
    story.event_seeded = False
    session.commit()
    ai = MockAIClient(seed=2)

    event_seed.refresh(session, ai)

    assert "書き直した筋書き" in ai.calls[0]["prompt"]
    assert story.event_seeded


def test_sources_are_drawn_again_when_the_ai_fails(session):
    story = _story(session)
    event_seed.refresh(session, _Fails(seed=1))
    assert not story.event_seeded
    ai = MockAIClient(seed=1)

    event_seed.refresh(session, ai)

    assert len(ai.calls) == 1
    assert story.event_seeded


def test_sources_are_split_by_letters(session, monkeypatch):
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_BATCH_LETTERS", 10)
    for text in ("あ" * 6, "い" * 6, "う" * 3):
        _story(session, text)
    ai = MockAIClient(seed=1)

    event_seed.refresh(session, ai)

    assert len(ai.calls) == 2
    assert "い" * 6 in ai.calls[1]["prompt"] and "う" * 3 in ai.calls[1]["prompt"]


def test_draw_picks_distinct_seeds_at_random(session):
    session.add_all([EventSeed(text=f"種{i}") for i in range(5)])
    session.commit()

    drawn = event_seed.draw(session, random.Random(1), 3)

    assert len(drawn) == len(set(drawn)) == 3
    assert len(event_seed.draw(session, random.Random(1), 10)) == 5


def test_draw_from_an_empty_pool_is_empty(session):
    assert event_seed.draw(session, random.Random(1)) == []


class _Merges(MockAIClient):
    def __init__(self, merges, seed=1):
        super().__init__(seed=seed)
        self.merges = merges

    def try_generate_json(self, prompt, schema, **kwargs):
        super().try_generate_json(prompt, schema, **kwargs)
        return {"merges": self.merges}


def _seeds(session, texts, *, consolidated=False) -> list[EventSeed]:
    seeds = [EventSeed(text=text, consolidated=consolidated) for text in texts]
    session.add_all(seeds)
    session.commit()
    return seeds


def _texts(session) -> dict[str, bool]:
    return {seed.text: seed.consolidated for seed in session.query(EventSeed).all()}


def test_consolidation_waits_until_enough_fresh_seeds(session, monkeypatch):
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_CONSOLIDATE_EVERY", 3)
    _seeds(session, ["甲", "乙"])
    ai = _Merges([{"numbers": [1, 2], "text": "甲乙"}])

    assert event_seed.consolidate(session, ai) == 0
    assert ai.calls == []


def test_similar_seeds_are_merged_and_the_rest_are_marked(session, monkeypatch):
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_CONSOLIDATE_EVERY", 3)
    _seeds(session, ["既存"], consolidated=True)
    _seeds(session, ["新一", "新二", "新三"])
    # 番号は 新一=1 新二=2 新三=3 既存=4
    ai = _Merges([{"numbers": [1, 4], "text": "新一と既存"}])

    removed = event_seed.consolidate(session, ai)

    assert removed == 1
    assert _texts(session) == {"新一と既存": True, "新二": True, "新三": True}
    prompt = ai.calls[0]["prompt"]
    assert "## 新しい種\n1. 新一\n2. 新二\n3. 新三\n\n## 棚卸し済みの種\n4. 既存" in prompt
    assert ai.calls[0]["system"] == event_seed._CONSOLIDATE_SYSTEM_PROMPT


def test_invalid_merges_are_ignored(session, monkeypatch):
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_CONSOLIDATE_EVERY", 2)
    _seeds(session, ["既存一", "既存二"], consolidated=True)
    _seeds(session, ["新一", "新二"])
    ai = _Merges([
        {"numbers": [3, 4], "text": "棚卸し済みどうし"},
        {"numbers": [1], "text": "一件だけ"},
        {"numbers": [1, 9], "text": "無い番号"},
        {"numbers": [1, 2], "text": ""},
        {"numbers": [1, 3], "text": "新一と既存一"},
        {"numbers": [1, 2], "text": "使った番号をもう一度"},
    ])

    event_seed.consolidate(session, ai)

    assert _texts(session) == {"新一と既存一": True, "既存二": True, "新二": True}


def test_settled_seeds_are_split_and_the_fresh_ones_come_along_each_time(session, monkeypatch):
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_CONSOLIDATE_EVERY", 2)
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_CONSOLIDATE_LETTERS", 4)
    _seeds(session, ["あああ", "いいい"], consolidated=True)
    _seeds(session, ["新一", "新二"])
    ai = _Merges([{"numbers": [1, 3], "text": "新一とあああ"}])

    event_seed.consolidate(session, ai)

    assert len(ai.calls) == 2
    assert "1. 新一" in ai.calls[0]["prompt"] and "3. あああ" in ai.calls[0]["prompt"]
    # 一回目でまとめた新一は、二回目には添えない
    assert "新一" not in ai.calls[1]["prompt"] and "1. 新二" in ai.calls[1]["prompt"]
    assert "2. いいい" in ai.calls[1]["prompt"]


def test_fresh_seeds_stay_unmarked_when_the_ai_fails(session, monkeypatch):
    monkeypatch.setattr(event_seed.constants, "EVENT_SEED_CONSOLIDATE_EVERY", 2)
    _seeds(session, ["新一", "新二"])

    assert event_seed.consolidate(session, _Fails(seed=1)) == 0
    assert _texts(session) == {"新一": False, "新二": False}


def test_update_event_seed_rewrites_the_text(session):
    record = EventSeed(text="いつか一党を組もうと言い合う。", consolidated=True)
    session.add(record)
    session.commit()

    result = UpdateEventSeed({"id": record.id, "text": "いつかチームを組もうと言い合う。"}).run()

    assert result["text"] == "いつかチームを組もうと言い合う。" and result["consolidated"] is True
    with pytest.raises(ValueError, match="id は必須"):
        UpdateEventSeed({"text": "種"}).run()
    with pytest.raises(UnknownRecordError):
        UpdateEventSeed({"id": record.id + 1, "text": "種"}).run()
