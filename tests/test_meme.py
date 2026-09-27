import random

import pytest

from ai.claude_code import ai_client
from ai.claude_code.interface.meme.draw_memes import DrawMemes
from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from ai.claude_code.interface.randomizer.commit_oracle import CommitOracle
from ai.claude_code.interface.randomizer.delete_meme import DeleteMeme
from ai.claude_code.interface.randomizer.update_meme import UpdateMeme
from ai.claude_code.interface.randomizer.update_oracle import UpdateOracle
from ai.time_keeper import constants, meme
from data_access_logic.query import meme_query
from db.schema import MEME_CATEGORIES, Character, ConfirmStatus, Event, Idea, Meme, Oracle
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


class _Fails(MockAIClient):
    def try_generate_json(self, prompt, schema, **kwargs):
        super().try_generate_json(prompt, schema, **kwargs)
        return {}


class _NoMemes(MockAIClient):
    def try_generate_json(self, prompt, schema, **kwargs):
        super().try_generate_json(prompt, schema, **kwargs)
        return {"memes": []}


class _Scripted(MockAIClient):
    def __init__(self, answers: dict):
        super().__init__(seed=1)
        self.answers = answers

    def try_generate_json(self, prompt, schema, **kwargs):
        super().try_generate_json(prompt, schema, **kwargs)
        return self.answers.get(kwargs.get("system"), {})

    def calls_for(self, system):
        return [call for call in self.calls if call["system"] == system]


def _extracted(*memes):
    return {meme._SYSTEM_PROMPT: {"memes": [{"text": text, "category": category} for text, category in memes]}}


def _idea(session, text="語の説明") -> Idea:
    idea = Idea(name="語", kind="用語", text=text)
    session.add(idea)
    session.commit()
    return idea


def _oracle(session, text="覚え書き") -> Oracle:
    oracle = Oracle(text=text)
    session.add(oracle)
    session.commit()
    return oracle


def test_memes_are_drawn_out_of_ideas_oracles_character_plots_and_events(session):
    idea = _idea(session)
    oracle = _oracle(session)
    planned = Character(name="甲", text="説明\n\n# plot\n\n起: 旅に出る\n\n# 来歴\n\n村の生まれ")
    unplanned = Character(name="乙", text="説明だけ")
    event = Event(name="別れ", text="甲は家を捨てて旅に出た", time=Stamp(2100))
    unwritten = Event(name="まだ書いていない", text="", time=Stamp(2100))
    session.add_all([planned, unplanned, event, unwritten])
    session.commit()
    ai = MockAIClient(seed=1)

    added = meme.refresh(session, ai)

    assert added == session.query(Meme).count()
    assert all(record.meme_seeded for record in (idea, oracle, planned, event))
    # 筋書きの節が無い人物・本文の無い出来事は、書かれるまで印を立てない
    assert not unplanned.meme_seeded and not unwritten.meme_seeded
    prompt = ai.calls[0]["prompt"]
    assert "語の説明" in prompt and "覚え書き" in prompt
    assert "起: 旅に出る" in prompt and "村の生まれ" not in prompt
    assert "## 元4(event)\n甲は家を捨てて旅に出た" in prompt
    assert ai.calls[0]["system"] == meme._SYSTEM_PROMPT


def test_unseeded_records_are_the_ones_not_flagged(session):
    seeded = _idea(session, "一つ目")
    unseeded = _idea(session, "二つ目")
    seeded.meme_seeded = True
    session.commit()

    rows = session.scalars(meme_query.unseeded_select(Idea)).all()

    assert [row.id for row in rows] == [unseeded.id]


def test_unconfirmed_memes_select_finds_only_the_unconfirmed(session):
    confirmed = Meme(text="確かめた", category="信条", confirmed=ConfirmStatus.APPROVED)
    unconfirmed = Meme(text="未確認", category="信条")
    session.add_all([confirmed, unconfirmed])
    session.commit()

    rows = session.scalars(meme_query.unconfirmed_memes_select()).all()

    assert [row.id for row in rows] == [unconfirmed.id]


def test_a_source_is_drawn_only_once_even_without_memes_or_after_edits(session):
    idea = _idea(session)
    meme.refresh(session, _NoMemes(seed=1))
    idea.text = "書き直した説明"
    session.commit()
    ai = MockAIClient(seed=1)

    assert meme.refresh(session, ai) == 0
    assert ai.calls == []


def test_clearing_the_flag_draws_the_source_again(session):
    idea = _idea(session)
    meme.refresh(session, MockAIClient(seed=1))
    idea.text = "書き直した説明"
    idea.meme_seeded = False
    session.commit()
    ai = MockAIClient(seed=2)

    meme.refresh(session, ai)

    assert "書き直した説明" in ai.calls[0]["prompt"]
    assert idea.meme_seeded


def test_sources_are_drawn_again_when_the_ai_fails(session):
    idea = _idea(session)
    meme.refresh(session, _Fails(seed=1))
    assert not idea.meme_seeded
    ai = MockAIClient(seed=1)

    meme.refresh(session, ai)

    assert len(ai.calls) == 1
    assert idea.meme_seeded


def test_sources_are_split_by_letters(session, monkeypatch):
    monkeypatch.setattr(meme.constants, "MEME_BATCH_LETTERS", 10)
    for text in ("あ" * 6, "い" * 6, "う" * 3):
        _idea(session, text)
    ai = MockAIClient(seed=1)

    meme.refresh(session, ai)

    assert len(ai.calls) == 2
    assert "い" * 6 in ai.calls[1]["prompt"] and "う" * 3 in ai.calls[1]["prompt"]


def test_category_descriptions_cover_every_category():
    assert tuple(meme.CATEGORY_DESCRIPTIONS) == MEME_CATEGORIES
    assert all(name in meme._SYSTEM_PROMPT for name in MEME_CATEGORIES)


def test_extracted_memes_keep_their_category(session):
    _idea(session)
    ai = _Scripted({**_extracted(("約束を守る", "信条"), ("空を目指す", "欲求")),
                    meme._DEDUPE_SYSTEM_PROMPT: {"duplicates": []}})

    assert meme.refresh(session, ai) == 2

    assert {m.text: m.category for m in session.query(Meme)} == {"約束を守る": "信条", "空を目指す": "欲求"}
    assert all(m.confirmed == ConfirmStatus.PENDING for m in session.query(Meme))


def test_a_meme_with_the_same_wording_is_dropped_without_asking(session):
    session.add(Meme(text="約束を守る。", category="信条"))
    idea = _idea(session)
    ai = _Scripted(_extracted(("約束を 守る", "信条")))

    assert meme.refresh(session, ai) == 0

    assert session.query(Meme).count() == 1
    assert ai.calls_for(meme._DEDUPE_SYSTEM_PROMPT) == []
    assert idea.meme_seeded


def test_memes_the_ai_marks_as_duplicates_are_not_added(session):
    session.add(Meme(text="約束は必ず守る", category="信条"))
    _idea(session)
    ai = _Scripted({**_extracted(("約束を違えない", "信条"), ("空を目指す", "欲求")),
                    meme._DEDUPE_SYSTEM_PROMPT: {"duplicates": [1]}})

    assert meme.refresh(session, ai) == 1

    assert sorted(m.text for m in session.query(Meme)) == ["空を目指す", "約束は必ず守る"]
    prompt = ai.calls_for(meme._DEDUPE_SYSTEM_PROMPT)[0]["prompt"]
    assert "1. 約束を違えない" in prompt and "- 約束は必ず守る" in prompt


def test_existing_memes_are_compared_in_chunks(session, monkeypatch):
    monkeypatch.setattr(meme.constants, "MEME_DEDUPE_LETTERS", 5)
    session.add_all([Meme(text="あ" * 5, category="信条"), Meme(text="い" * 5, category="信条")])
    _idea(session)
    ai = _Scripted({**_extracted(("う" * 5, "欲求")), meme._DEDUPE_SYSTEM_PROMPT: {"duplicates": []}})

    assert meme.refresh(session, ai) == 1

    prompts = [call["prompt"] for call in ai.calls_for(meme._DEDUPE_SYSTEM_PROMPT)]
    assert len(prompts) == 2
    assert "あ" * 5 in prompts[0] and "い" * 5 in prompts[1]


def test_sources_are_drawn_again_when_the_duplicate_check_fails(session):
    session.add(Meme(text="約束は必ず守る", category="信条"))
    idea = _idea(session)
    ai = _Scripted(_extracted(("約束を違えない", "信条")))

    assert meme.refresh(session, ai) == 0

    assert session.query(Meme).count() == 1
    assert not idea.meme_seeded


def test_memes_without_a_category_are_classified(session):
    hand_written = Meme(text="手で書いたミーム")
    unanswered = Meme(text="分類の外を答えられたミーム")
    placed = Meme(text="置き場所を決めたミーム")
    session.add_all([hand_written, unanswered, placed])
    session.commit()
    ai = _Scripted({meme._CLASSIFY_SYSTEM_PROMPT: {"categories": [
        {"number": 1, "category": "境遇"}, {"number": 2, "category": "不明"}, {"number": 3, "category": "理"}]}})

    meme.refresh(session, ai)

    assert (hand_written.category, unanswered.category, placed.category) == ("境遇", None, "理")
    assert "1. 手で書いたミーム" in ai.calls_for(meme._CLASSIFY_SYSTEM_PROMPT)[0]["prompt"]


def _memes_in_every_category(session, count=3):
    session.add_all([Meme(text=f"{category}{i}", category=category, confirmed=ConfirmStatus.APPROVED)
                     for category in MEME_CATEGORIES for i in range(count)])
    session.commit()


def test_draw_takes_zero_to_two_per_category_with_a_position(session):
    _memes_in_every_category(session)
    counts = set()

    for seed in range(30):
        drawn = meme.draw(session, random.Random(seed), constants.MEME_PERSON_CATEGORIES)
        for category in constants.MEME_PERSON_CATEGORIES:
            picked = [item for item in drawn if item["category"] == category]
            counts.add(len(picked))
            assert len({item["id"] for item in picked}) == len(picked)
        assert {item["category"] for item in drawn} <= set(constants.MEME_PERSON_CATEGORIES)
        assert all(item["position"] in constants.MEME_POSITIONS for item in drawn)
        assert all(item["text"] == session.get(Meme, item["id"]).text for item in drawn)

    assert counts == {0, 1, 2}


def test_draw_never_takes_laws_and_skips_empty_categories(session):
    session.add_all([Meme(text="世界の法則", category="理", confirmed=ConfirmStatus.APPROVED),
                      Meme(text="組織の論理", category="集団", confirmed=ConfirmStatus.APPROVED)])
    session.commit()
    categories = {item["category"]
                  for seed in range(30)
                  for item in meme.draw(session, random.Random(seed), constants.MEME_NON_PERSON_CATEGORIES)}
    assert categories == {"集団"}
    assert "理" not in constants.MEME_PERSON_CATEGORIES + constants.MEME_NON_PERSON_CATEGORIES


def test_draw_never_takes_unconfirmed_memes(session):
    session.add(Meme(text="未確認の信条", category="信条", confirmed=ConfirmStatus.PENDING))
    session.commit()

    for seed in range(30):
        assert meme.draw(session, random.Random(seed), constants.MEME_PERSON_CATEGORIES) == []


def test_meme_section_lists_position_and_text():
    drawn = [{"position": "裏", "text": "隠して守る"}, {"position": "古", "text": "届け出る"}]
    assert meme.meme_section(drawn) == "- 裏: 隠して守る\n- 古: 届け出る"


def test_draw_memes_entrypoint_uses_the_categories_for_its_kind(session):
    _memes_in_every_category(session)

    person = {item["category"] for seed in range(20) for item in DrawMemes(person=True, seed=seed).run()}
    non_person = {item["category"] for seed in range(20) for item in DrawMemes(person=False, seed=seed).run()}

    assert person == set(constants.MEME_PERSON_CATEGORIES)
    assert non_person == set(constants.MEME_NON_PERSON_CATEGORIES)
    assert DrawMemes(seed=3).run() == DrawMemes(seed=3).run()


def test_update_meme_changes_given_columns(session):
    record = Meme(text="約束を守る")
    session.add(record)
    session.commit()

    result = UpdateMeme({"id": record.id, "category": "信条"}).run()

    assert result["category"] == "信条" and result["text"] == "約束を守る"
    with pytest.raises(ValueError, match="category は"):
        UpdateMeme({"id": record.id, "category": "不明"}).run()
    with pytest.raises(ValueError, match="id は必須"):
        UpdateMeme({"category": "信条"}).run()


def test_delete_meme_removes_it(session):
    record = Meme(text="約束を守る", category="信条")
    session.add(record)
    session.commit()

    meme_id = record.id

    assert DeleteMeme(meme_id).run() == {"id": meme_id, "category": "信条", "text": "約束を守る"}

    session.expire_all()
    assert session.get(Meme, meme_id) is None


def test_commit_oracle_adds_a_note(session):
    result = CommitOracle({"text": "覚え書き", "title": "題"}).run()

    record = session.get(Oracle, result["id"])
    assert (record.text, record.title) == ("覚え書き", "題")
    assert not record.meme_seeded
    with pytest.raises(ValueError, match="text は必須"):
        CommitOracle({"title": "空"}).run()


@pytest.mark.parametrize("entrypoint, payload, model", [
    (CommitOracle, {"text": "約束は破らない"}, Oracle),
    (CommitIdea, {"name": "誓約", "kind": "概念", "text": "約束は破らない"}, Idea),
])
def test_commit_extracts_memes_right_away(session, monkeypatch, entrypoint, payload, model):
    monkeypatch.setattr(ai_client, "try_generate_json", _Scripted({
        meme._SYSTEM_PROMPT: {"memes": [{"text": "約束を守る", "category": "信条"}]},
        meme._DEDUPE_SYSTEM_PROMPT: {"duplicates": []},
    }).try_generate_json)

    result = entrypoint(payload).run()

    assert result["memes_added"] == 1
    assert [(m.text, m.category) for m in session.query(Meme).all()] == [("約束を守る", "信条")]
    session.expire_all()
    assert session.get(model, result["id"]).meme_seeded


def test_commit_is_kept_when_meme_extraction_fails(session):
    result = CommitIdea({"name": "誓約", "kind": "概念", "text": "約束は破らない"}).run()

    assert result["memes_added"] == 0
    record = session.get(Idea, result["id"])
    assert record is not None and not record.meme_seeded


def test_update_oracle_changes_given_columns(session):
    record = _oracle(session, "前の覚え書き")

    result = UpdateOracle({"id": record.id, "text": "書き足した覚え書き"}).run()

    assert result["text"] == "書き足した覚え書き" and result["meme_seeded"] is False
    with pytest.raises(ValueError, match="空にはできない"):
        UpdateOracle({"id": record.id, "text": ""}).run()
    with pytest.raises(ValueError, match="id=999"):
        UpdateOracle({"id": 999, "text": "無い"}).run()
