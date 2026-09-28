"""アイデアの作中での呼び名(`idea_recognition`)と、場所・時代による呼び名の選び方(`idea_alias`)。"""
import pytest

from ai.claude_code.interface.idea.resolve_terms import ResolveTerms
from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from ai.claude_code.interface.randomizer.delete_idea import DeleteIdea
from ai.claude_code.interface.randomizer.merge_idea import MergeIdea
from ai.claude_code.interface.randomizer.update_idea import UpdateIdea
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.world.search_ideas import SearchIdeas
from ai.time_keeper import idea_alias, idea_context, idea_search
from db.schema import Idea, IdeaRecognition, Location
from db.stamp import Stamp


@pytest.fixture
def places(session):
    world = Location(name="世界線", kind="世界線", text="")
    session.add(world)
    session.flush()
    village = Location(name="村", kind="村", parent_id=world.id, text="", start=Stamp(2000))
    other = Location(name="別の世界線", kind="世界線", text="")
    session.add_all([village, other])
    session.commit()
    return {"world": world, "village": village, "other": other}


def _idea(session, name, text="", kind="技術", **columns):
    record = Idea(name=name, kind=kind, text=text, **columns)
    session.add(record)
    session.commit()
    return record


def _recognition(session, idea, name, detail=None, **columns):
    record = IdeaRecognition(idea_id=idea.id, name=name, detail=detail, **columns)
    session.add(record)
    session.commit()
    return record


@pytest.fixture
def energy(session, places):
    """本質のアイデア「エナジー」は別の世界線に置き、村のある世界線では呼び名だけが効く。"""
    return _idea(session, "エナジー", "化学エネルギーとして溜める", location_id=places["other"].id)


# ---------------------------------------------------------------- 呼び名の選び方

def test_recognition_matching_the_place_and_time_is_chosen(session, places, energy):
    recognition = _recognition(session, energy, "魔力", "住人は魔法の力だと思っている",
                               location_id=places["world"].id, start=Stamp(2000))

    called = idea_alias.called(session, [energy.id], places["village"].id, "2100")

    assert called == {energy.id: recognition}
    assert idea_alias.name_of(energy, called) == "魔力"
    assert idea_alias.text_of(energy, called) == "住人は魔法の力だと思っている 化学エネルギーとして溜める"


def test_essence_name_is_used_when_no_recognition_matches(session, places, energy):
    _recognition(session, energy, "魔力", location_id=places["world"].id, start=Stamp(2200))
    _recognition(session, energy, "霊力", location_id=places["other"].id)

    called = idea_alias.called(session, [energy.id], places["village"].id, "2100")

    assert called == {}
    assert idea_alias.name_of(energy, called) == "エナジー"


def test_empty_columns_of_a_recognition_match_any_place_and_time(session, places, energy):
    recognition = _recognition(session, energy, "力")

    assert idea_alias.called(session, [energy.id], places["village"].id, "2100") == {energy.id: recognition}
    assert idea_alias.called(session, [energy.id]) == {energy.id: recognition}


def test_without_place_or_time_only_recognitions_with_empty_columns_match(session, places, energy):
    _recognition(session, energy, "魔力", location_id=places["world"].id)
    _recognition(session, energy, "旧名", end=Stamp(2000))

    assert idea_alias.called(session, [energy.id]) == {}


def test_nearer_place_then_later_start_wins(session, places, energy):
    _recognition(session, energy, "力")
    _recognition(session, energy, "魔力", location_id=places["world"].id)
    old = _recognition(session, energy, "気", location_id=places["village"].id, start=Stamp(2000))
    new = _recognition(session, energy, "霊気", location_id=places["village"].id, start=Stamp(2050))

    assert idea_alias.called(session, [energy.id], places["village"].id, "2100") == {energy.id: new}
    assert idea_alias.called(session, [energy.id], places["village"].id, "2020") == {energy.id: old}


# ---------------------------------------------------------------- 各処理

def test_resolve_hitting_a_recognition_returns_the_essence_called_by_it(session, places, energy):
    energy.start = Stamp(1000)
    session.commit()
    recognition = _recognition(session, energy, "魔力", "住人は魔法の力だと思っている",
                               location_id=places["world"].id)

    context = idea_context.resolve(session, ["魔力"], places["village"].id, "2100")
    section = idea_context.prompt_section(context.related, context.called)

    assert context.hits == [energy]
    assert context.related == [energy]
    assert context.called == {energy.id: recognition}
    assert "- 魔力(技術): 住人は魔法の力だと思っている 化学エネルギーとして溜める" in section
    assert "エナジー" not in section


def test_brief_lists_the_essence_once_by_its_recognition(session, places):
    essence = _idea(session, "エナジー", "化学エネルギーとして溜める", location_id=places["world"].id)
    _recognition(session, essence, "魔力", location_id=places["world"].id)

    ideas = _rows.brief(session, places["village"].id, "2100")["ideas"]

    assert [(idea["id"], idea["name"]) for idea in ideas] == [(essence.id, "魔力")]


def test_search_and_resolve_entries_return_the_called_name(session, places, energy):
    _recognition(session, energy, "魔力", location_id=places["world"].id)

    rows = SearchIdeas(["魔力"], place_id=places["village"].id).run()
    resolved = ResolveTerms(["魔力"], places["village"].id).run()

    assert [(row["id"], row["called"]) for row in rows] == [(energy.id, "魔力")]
    assert [(row["id"], row["called"]) for row in resolved["ideas"]] == [(energy.id, "魔力")]


def test_idea_search_matches_by_recognition_name(session, places, energy):
    _recognition(session, energy, "魔力", location_id=places["world"].id)

    hits = idea_search.search(session, ["魔力"], places["village"].id, "2100")

    assert [hit.idea.id for hit in hits] == [energy.id]


# ---------------------------------------------------------------- 入口の検証

def test_commit_and_update_idea_accept_recognitions(session, places):
    created = CommitIdea({
        "name": "エナジー", "kind": "技術", "text": "元の力",
        "recognitions": [{"name": "魔力", "location_id": places["world"].id,
                          "detail": "住人は魔法の力だと思っている"}],
    }).run()
    idea_id = created["id"]
    session.expire_all()
    assert [r.name for r in session.get(Idea, idea_id).recognitions] == ["魔力"]

    UpdateIdea({"id": idea_id, "recognitions": [{"name": "力"}]}).run()
    session.expire_all()
    assert [r.name for r in session.get(Idea, idea_id).recognitions] == ["力"]


def test_merge_moves_recognitions_to_the_target(session, energy):
    recognition = _recognition(session, energy, "魔力")
    target = _idea(session, "エネルギー")
    recognition_id, energy_id, target_id = recognition.id, energy.id, target.id

    MergeIdea(energy_id, target_id).run()

    session.expire_all()
    assert session.get(Idea, energy_id) is None
    assert session.get(IdeaRecognition, recognition_id).idea_id == target_id


def test_delete_removes_its_recognitions(session, energy):
    recognition = _recognition(session, energy, "魔力")
    recognition_id, energy_id = recognition.id, energy.id

    DeleteIdea(energy_id).run()

    session.expire_all()
    assert session.get(Idea, energy_id) is None
    assert session.get(IdeaRecognition, recognition_id) is None
