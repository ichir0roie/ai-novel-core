"""アイデアのあいまい検索(`idea_search`)と、下書きと清書のあいだの中間段(`idea_context`)。"""
import random

import pytest

from ai.claude_code import story_writer
from ai.time_keeper import character_event_generator, episode_summary, idea_context, idea_search, meme, random_character_generator
from data_access_logic.idea.delete_idea import DeleteIdea
from data_access_logic.idea.link_ideas import LinkIdeas
from data_access_logic.idea.merge_idea import MergeIdea
from data_access_logic.idea.resolve_terms import ResolveTerms
from data_access_logic.idea.search_ideas import SearchIdeas
from data_access_logic.story import reading
from db.schema import (
    Character, CharacterIdea, CharacterPlace, ConfirmStatus, Episode, EpisodeIdea, Event, EventIdea, Idea,
    Location, Story,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


class _Terms(MockAIClient):
    """語の洗い出しには `terms` を、清書(人物)には `polished` を返す。ほかはモックのまま。"""

    def __init__(self, terms, polished="清書した説明"):
        super().__init__(seed=1)
        self.terms = terms
        self.polished = polished

    def try_generate_json(self, prompt, schema, **kwargs):
        decided = super().try_generate_json(prompt, schema, **kwargs)
        if schema is idea_search._SCHEMA:
            return {"terms": self.terms}
        if schema is random_character_generator._POLISH_SCHEMA:
            return {"text": self.polished}
        return decided

    def calls_for(self, schema):
        return [call for call in self.calls if call["schema"] is schema]


@pytest.fixture
def places(session):
    world = Location(name="世界線", kind="世界線", text="")
    session.add(world)
    session.flush()
    planet = Location(name="星", kind="星", parent_id=world.id, text="")
    session.add(planet)
    session.flush()
    village = Location(name="村", kind="村", parent_id=planet.id, text="山あいの村", start=Stamp(2000),
                       active_random_generation=True)
    other = Location(name="別の世界線", kind="世界線", text="")
    session.add_all([village, other])
    session.commit()
    return {"world": world, "planet": planet, "village": village, "other": other}


def _idea(session, name, text="", kind="技術", **columns):
    record = Idea(name=name, kind=kind, text=text, **columns)
    session.add(record)
    session.commit()
    return record


# ---------------------------------------------------------------- 検索

def test_search_ranks_name_over_variant_over_text(session):
    body = _idea(session, "寄生治療", "宿主の細胞を置き換える")
    variant = _idea(session, "遺伝病", "血の病")
    name = _idea(session, "遺伝子異常", "世代を重ねると出る")

    hits = idea_search.search(session, [{"keyword": "遺伝子異常", "variants": ["遺伝病", "細胞"]}])

    assert [(hit.idea.id, hit.score) for hit in hits] == [(name.id, 3), (variant.id, 2), (body.id, 1)]
    assert hits[0].keywords == ["遺伝子異常"]


def test_search_sums_scores_over_keywords(session):
    both = _idea(session, "虫憑き", "寄生の治療")
    one = _idea(session, "寄生", "")

    hits = idea_search.search(session, ["虫憑き", "寄生"])

    assert [(hit.idea.id, hit.score) for hit in hits] == [(both.id, 4), (one.id, 3)]


def test_search_matches_the_other_kana_and_full_width(session):
    katakana = _idea(session, "ヒナタ", "")
    ascii_name = _idea(session, "HINATA式", "")

    assert [hit.idea.id for hit in idea_search.search(session, ["ひなた"])] == [katakana.id]
    assert [hit.idea.id for hit in idea_search.search(session, ["ＨＩＮＡＴＡ"])] == [ascii_name.id]


def test_search_does_not_treat_like_wildcards_as_wildcards(session):
    _idea(session, "魔力", "")

    assert idea_search.search(session, ["%"]) == []


def test_search_is_limited_to_the_scope_of_the_place(session, places):
    inside = _idea(session, "魔力", location_id=places["world"].id)
    _idea(session, "魔力炉", location_id=places["other"].id)

    hits = idea_search.search(session, ["魔力"], place_id=places["village"].id)

    assert [hit.idea.id for hit in hits] == [inside.id]


def test_search_does_not_reach_ideas_placed_below_the_place(session, places):
    above = _idea(session, "魔力", location_id=places["planet"].id)
    _idea(session, "魔力溜まり", location_id=places["village"].id)

    hits = idea_search.search(session, ["魔力"], place_id=places["planet"].id)

    assert [hit.idea.id for hit in hits] == [above.id]


def test_search_is_limited_to_ideas_in_effect_at_the_time(session):
    always = _idea(session, "魔力")
    _idea(session, "魔力炉", start=Stamp(2100))
    ended = _idea(session, "魔力灯", end=Stamp(2050))
    current = _idea(session, "魔力網", start=Stamp(2000), end=Stamp(2100))

    hits = idea_search.search(session, ["魔力"], time="2050")

    assert sorted(hit.idea.id for hit in hits) == [always.id, current.id]
    assert ended.id in [hit.idea.id for hit in idea_search.search(session, ["魔力"], time="2049/12/31")]


def test_search_excludes_unconfirmed_ideas_by_default(session):
    _idea(session, "虫憑き", kind="呼称", confirmed=ConfirmStatus.PENDING)

    assert idea_search.search(session, ["虫憑き"]) == []


def test_search_includes_unconfirmed_ideas_when_asked(session):
    _idea(session, "虫憑き", kind="呼称", confirmed=ConfirmStatus.PENDING)

    hits = idea_search.search(session, ["虫憑き"], confirmed_only=False)

    assert [hit.idea.name for hit in hits] == ["虫憑き"]


def test_search_ideas_entry_takes_keywords_with_variants(session, places):
    idea = _idea(session, "遺伝子異常", "", location_id=places["world"].id)

    rows = SearchIdeas([{"keyword": "血の病", "variants": ["遺伝子"]}], place_id=places["village"].id).run()

    assert [(row["id"], row["score"], row["keywords"]) for row in rows] == [(idea.id, 2, ["血の病"])]


def test_terms_are_normalized_and_deduplicated():
    terms = idea_search.terms_of(
        ["語", {"keyword": " 語 "}, {"keyword": "虫", "variants": ["虫", "むし", "官", ""]}, 3])

    assert terms == [{"keyword": "語", "variants": [], "description": "", "coined": True, "kind": "概念",
                      "start": None, "end": None},
                     {"keyword": "虫", "variants": ["むし"], "description": "", "coined": True, "kind": "概念",
                      "start": None, "end": None}]


def test_term_periods_are_parsed_and_unreadable_ones_dropped():
    terms = idea_search.terms_of([
        {"keyword": "宿り", "start": "2090/04/01", "end": "2150"},
        {"keyword": "虫憑き", "start": "昔", "end": None},
        {"keyword": "寄生", "start": "2100", "end": "2100"},
    ])

    assert [(term["start"], term["end"]) for term in terms] == [
        (Stamp(2090, 4, 1), Stamp(2150)), (None, None), (Stamp(2100), None)]


def test_keywords_are_asked_with_the_time_of_the_text():
    ai = _Terms([{"keyword": "宿り", "variants": [], "description": "", "coined": True, "kind": "技術",
                  "start": "2090", "end": None}])

    [term] = idea_search.keywords_of("虫を宿す", ai, "2100/04/01")

    assert "この文の時刻: 2100/04/01" in ai.calls[0]["prompt"]
    assert (term["start"], term["end"]) == (Stamp(2090), None)


def test_keywords_are_not_asked_for_an_empty_text():
    ai = _Terms([{"keyword": "語", "variants": [], "description": ""}])

    assert idea_search.keywords_of("  ", ai) == []
    assert ai.calls == []


# ---------------------------------------------------------------- 中間段

def test_resolve_returns_hits_with_their_parents_and_children(session, places):
    parent = _idea(session, "正常化アプローチ", "寄生系とウイルス系", location_id=places["world"].id)
    hit = _idea(session, "寄生型", "悪魔のデータベースにあった", location_id=places["world"].id,
                parent_idea_id=parent.id)
    child = _idea(session, "虫憑き", "地上の呼び名", location_id=places["world"].id,
                  parent_idea_id=hit.id)
    _idea(session, "外の呼び名", location_id=places["other"].id, parent_idea_id=hit.id)

    context = idea_context.resolve(session, [{"keyword": "寄生型"}], places["village"].id)

    assert [idea.id for idea in context.hits] == [hit.id]
    assert [idea.id for idea in context.related] == [hit.id, parent.id, child.id]
    assert context.candidates == []


def test_resolve_at_a_time_leaves_undated_ideas_out_of_the_references(session, places):
    undated = _idea(session, "奇跡", "地下が地上に配る", location_id=places["world"].id)
    dated = _idea(session, "奇跡の型", "書き込む型", location_id=places["world"].id,
                  parent_idea_id=undated.id, start=Stamp(2050))

    context = idea_context.resolve(
        session, [{"keyword": "奇跡", "description": "", "kind": "技術"}], places["village"].id, "2100")

    assert {idea.id for idea in context.hits} == {undated.id, dated.id}
    assert [idea.id for idea in context.related] == [dated.id]
    # 語は当たっているので、同じ名の候補は足さない
    assert context.candidates == []


def test_unmatched_term_becomes_an_unconfirmed_idea_of_the_world(session, places):
    context = idea_context.resolve(
        session, [{"keyword": "宿り", "variants": ["寄生"], "description": "体に虫を宿す治療", "kind": "技術",
                   "start": "2090", "end": "2150"},
                  {"keyword": "虫憑き", "description": "宿りを受けた人", "kind": "呼称"}],
        places["village"].id, "2100/04/01")

    assert context.hits == [] and context.related == []
    [candidate, undated] = context.candidates
    assert (candidate.name, candidate.kind, candidate.text) == ("宿り", "技術", "体に虫を宿す治療")
    assert candidate.confirmed == ConfirmStatus.PENDING
    assert candidate.location_id == places["world"].id
    assert candidate.start == Stamp(2090) and candidate.end == Stamp(2150)
    # 時期のはっきりしない語は、出来事の時刻を入れずに空のままにする
    assert undated.start is None and undated.end is None


def test_unmatched_term_gets_the_existing_classification_as_parent(session, places):
    star = _idea(session, "星", "惑星のアイデア", kind="星", location_id=places["planet"].id)
    classification = _idea(session, "技術", "分類", kind="技術", location_id=places["planet"].id,
                           parent_idea_id=star.id)

    context = idea_context.resolve(
        session, [{"keyword": "宿り", "description": "治療", "kind": "技術"}], places["village"].id)

    [candidate] = context.candidates
    assert candidate.parent_idea_id == classification.id
    # 分類自体は新しく作られない(既存の一件のまま)
    assert session.query(Idea).filter_by(name="技術", kind="技術").count() == 1


def test_unmatched_term_creates_the_missing_classification(session, places):
    world_idea = _idea(session, "世界線", "ルートのアイデア", kind="世界線", location_id=places["world"].id)

    context = idea_context.resolve(
        session, [{"keyword": "宿り", "description": "治療", "kind": "技術"}], places["village"].id)

    [candidate] = context.candidates
    classification = session.get(Idea, candidate.parent_idea_id)
    assert classification.name == "技術" and classification.kind == "技術"
    assert classification.location_id == places["world"].id
    assert classification.parent_idea_id == world_idea.id
    assert classification.confirmed == ConfirmStatus.APPROVED


def test_unmatched_term_without_a_known_place_gets_no_parent(session):
    context = idea_context.resolve(
        session, [{"keyword": "宿り", "description": "治療", "kind": "技術"}], None)

    [candidate] = context.candidates
    assert candidate.parent_idea_id is None


def test_general_words_do_not_become_candidates(session, places):
    context = idea_context.resolve(
        session, [{"keyword": "鍛冶師", "variants": ["鍛冶"], "description": "", "coined": False}],
        places["village"].id)

    assert context.candidates == []
    assert session.query(Idea).count() == 0


def test_existing_candidate_is_reused(session, places):
    old = _idea(session, "ヤドリ", kind="技術", confirmed=ConfirmStatus.PENDING, start=Stamp(2200))

    context = idea_context.resolve(session, ["やどり"], places["village"].id, "2100")

    assert context.hits == []
    assert [idea.id for idea in context.candidates] == [old.id]
    assert session.query(Idea).count() == 1


def test_names_of_characters_and_places_do_not_become_candidates(session, places):
    session.add(Character(name="ノア", text=""))
    session.commit()

    context = idea_context.resolve(session, ["ノア", "村"], places["village"].id)

    assert context.candidates == []
    assert session.query(Idea).count() == 0


def test_unconfirmed_ideas_are_left_out_of_the_brief_but_still_meme_extracted(session, places):
    unconfirmed = _idea(session, "宿り", "体に虫を宿す治療", kind="技術", confirmed=ConfirmStatus.PENDING,
                        location_id=places["world"].id)
    confirmed = _idea(session, "魔力", "世界の力", location_id=places["world"].id)
    ai = MockAIClient(seed=1)

    names = [idea["name"] for idea in reading.brief(session, places["village"].id, "2100/01/01")["ideas"]]
    meme.refresh(session, ai)

    assert names == ["魔力"]
    assert unconfirmed.meme_seeded is True and confirmed.meme_seeded is True


def test_brief_leaves_out_ideas_not_in_effect_at_the_time(session, places):
    _idea(session, "魔力", location_id=places["world"].id, start=Stamp(2200))
    _idea(session, "寄生", location_id=places["world"].id, end=Stamp(2100))
    _idea(session, "宿り", location_id=places["world"].id, start=Stamp(2000), end=Stamp(2101))

    names = [idea["name"] for idea in reading.brief(session, places["village"].id, "2100")["ideas"]]

    assert names == ["宿り"]


def test_prompt_section_cuts_long_texts(session, monkeypatch):
    monkeypatch.setattr(idea_context.constants, "IDEA_CONTEXT_LETTERS", 3)
    idea = _idea(session, "魔力", "世界を巡る力")

    section = idea_context.prompt_section([idea])

    assert section.startswith("関係する設定:\n")
    assert "- 魔力(技術): 世界を…" in section
    assert idea_context.prompt_section([]) == ""


def test_link_skips_ideas_already_linked(session):
    event = Event(name="出来事", text="", time=Stamp(2100))
    session.add(event)
    session.commit()
    first = _idea(session, "魔力")
    second = _idea(session, "寄生")

    assert idea_context.link(session, event, [first]) == 1
    assert idea_context.link(session, event, [first, second]) == 1
    assert sorted(row.idea_id for row in session.query(EventIdea)) == [first.id, second.id]
    assert idea_context.linked_records(session, first.id)["event"] == [event]


# ---------------------------------------------------------------- 入口

def test_resolve_terms_entry_adds_candidates_and_link_ideas_links_them(session, places):
    known = _idea(session, "魔力", location_id=places["world"].id)
    event = Event(name="出来事", text="", time=Stamp(2100))
    session.add(event)
    session.commit()

    resolved = ResolveTerms(["魔力", {"keyword": "宿り", "description": "治療"}], places["village"].id).run()
    ids = resolved["hits"] + [row["id"] for row in resolved["candidates"]]
    linked = LinkIdeas(ids, event_id=event.id).run()

    assert [row["name"] for row in resolved["ideas"]] == ["魔力"]
    assert resolved["hits"] == [known.id]
    assert [row["name"] for row in resolved["candidates"]] == ["宿り"]
    assert linked == {"event_id": event.id, "linked": 2}


def test_link_ideas_takes_exactly_one_owner(session):
    with pytest.raises(ValueError):
        LinkIdeas([], event_id=1, episode_id=1).run()
    with pytest.raises(ValueError):
        LinkIdeas([]).run()


def test_merge_idea_moves_links_and_removes_the_source(session):
    character = Character(name="甲", text="")
    session.add(character)
    session.commit()
    candidate = _idea(session, "むしつき", kind="呼称", confirmed=ConfirmStatus.PENDING)
    target = _idea(session, "虫憑き")
    idea_context.link(session, character, [candidate, target])
    session.commit()
    candidate_id, target_id = candidate.id, target.id

    result = MergeIdea(candidate_id, target_id).run()

    session.expire_all()
    assert result["links_moved"] == 1
    assert session.get(Idea, candidate_id) is None
    assert [row.idea_id for row in session.query(CharacterIdea)] == [target_id]


def test_delete_idea_removes_its_links(session):
    event = Event(name="出来事", text="", time=Stamp(2100))
    session.add(event)
    session.commit()
    idea = _idea(session, "宿り", confirmed=ConfirmStatus.PENDING)
    idea_context.link(session, event, [idea])
    session.commit()

    DeleteIdea(idea.id).run()

    assert session.query(EventIdea).count() == 0


# ---------------------------------------------------------------- 生成への組み込み

def _sub_character(session, place):
    record = Character(name="甲", text="甲の説明", start=Stamp(2080))
    session.add(record)
    session.flush()
    session.add(CharacterPlace(character_id=record.id, location_id=place.id, start=Stamp(2080)))
    session.commit()
    return record


def test_daily_event_novel_is_told_the_ideas_and_the_event_is_linked(session, places):
    idea = _idea(session, "遺伝子異常", "世代を重ねると出る病", location_id=places["world"].id,
                 start=Stamp(2000))
    _sub_character(session, places["village"])
    ai = _Terms([{"keyword": "遺伝子異常", "variants": [], "description": ""},
                 {"keyword": "宿り", "variants": [], "description": "治療", "start": "2050"}])

    record = character_event_generator.generate_next(session, ai, random.Random(1))

    [terms_call] = ai.calls_for(idea_search._SCHEMA)
    assert record.name in terms_call["prompt"]
    assert f"この文の時刻: {record.time}" in terms_call["prompt"]
    novel = ai.calls[-1]
    assert novel["schema"] is character_event_generator._NOVEL_SCHEMA
    assert "関係する設定:" in novel["prompt"] and "世代を重ねると出る病" in novel["prompt"]
    linked = {row.idea_id for row in session.query(EventIdea).filter_by(event_id=record.id)}
    candidate = session.query(Idea).filter_by(name="宿り").one()
    assert linked == {idea.id, candidate.id}
    assert candidate.confirmed == ConfirmStatus.PENDING and candidate.start == Stamp(2050)


def test_daily_event_without_matching_ideas_tells_no_setting(session, places):
    _sub_character(session, places["village"])
    ai = _Terms([])

    character_event_generator.generate_next(session, ai, random.Random(1))

    assert "関係する設定" not in ai.calls[-1]["prompt"]
    assert session.query(EventIdea).count() == 0


def test_generated_character_is_polished_with_the_ideas_and_linked(session, places):
    idea = _idea(session, "遺伝子異常", "世代を重ねると出る病", location_id=places["world"].id,
                 start=Stamp(2000))
    session.add(Story(name="村の話", place_id=places["village"].id, text="村の筋書き", narration="",
                      state="構想中", start=Stamp(2000), end=Stamp(2300)))
    session.commit()
    ai = _Terms([{"keyword": "遺伝子異常", "variants": [], "description": ""}])

    record = random_character_generator._generate_one(
        session, places["village"], Stamp(2100, 1, 1), random.Random(1), ai, person=True)

    [polish] = ai.calls_for(random_character_generator._POLISH_SCHEMA)
    assert "世代を重ねると出る病" in polish["prompt"]
    assert record.text.startswith("清書した説明")
    assert [row.idea_id for row in session.query(CharacterIdea).filter_by(character_id=record.id)] == [idea.id]


def test_generated_character_is_not_polished_without_ideas(session, places):
    ai = _Terms([])

    random_character_generator._generate_one(
        session, places["village"], Stamp(2100, 1, 1), random.Random(1), ai, person=True)

    assert ai.calls_for(random_character_generator._POLISH_SCHEMA) == []


def test_seeded_episode_is_written_with_the_ideas_of_its_seed(session, places, monkeypatch):
    idea = _idea(session, "寄生型", "悪魔のデータベースにあった治療", location_id=places["world"].id,
                 start=Stamp(2000))
    story = Story(name="村の話", place_id=places["village"].id, text="筋書き", narration="三人称",
                  state="執筆中", start=Stamp(2100, 4, 1), end=Stamp(2300))
    session.add(story)
    session.flush()
    session.add(Episode(story_id=story.id, title="", key="1. 地下 / カシル / 寄生型を使う",
                        synced=False))
    session.commit()
    calls = []

    def fake(prompt, schema, *, system=None, timeout=None, options=None, **_):
        calls.append({"prompt": prompt, "schema": schema})
        if schema is idea_search._SCHEMA:
            return {"terms": [{"keyword": "寄生型", "variants": [], "description": ""}]}
        if schema is episode_summary._SCHEMA:
            return {"summary": "", "style": ""}
        return {"title": "題", "text": "本文"}

    monkeypatch.setattr(story_writer.ai_client, "try_generate_json", fake)

    record = story_writer.write_next_episode(session, story.id)

    assert "寄生型を使う" in calls[0]["prompt"]
    assert "関係する設定:" in calls[-1]["prompt"] and "悪魔のデータベースにあった治療" in calls[-1]["prompt"]
    assert [row.idea_id for row in session.query(EpisodeIdea).filter_by(episode_id=record.id)] == [idea.id]
