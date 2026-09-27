"""アイデアの作中での呼び名(`alias_of_idea_id`)と、場所・時代による呼び名の選び方(`idea_alias`)。"""
import pytest

from ai.claude_code.interface.idea.resolve_terms import ResolveTerms
from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from ai.claude_code.interface.randomizer.delete_idea import DeleteIdea
from ai.claude_code.interface.randomizer.merge_idea import MergeIdea
from ai.claude_code.interface.randomizer.update_idea import UpdateIdea
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.world.search_ideas import SearchIdeas
from ai.time_keeper import idea_alias, idea_context
from db.schema import Idea, IdeaNote, Location
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


@pytest.fixture
def energy(session, places):
    """本質のアイデア「エナジー」は別の世界線に置き、村のある世界線では呼び名だけが効く。"""
    return _idea(session, "エナジー", "化学エネルギーとして溜める", location_id=places["other"].id)


# ---------------------------------------------------------------- 呼び名の選び方

def test_alias_matching_the_place_and_time_is_chosen(session, places, energy):
    alias = _idea(session, "魔力", "住人は魔法の力だと思っている", kind="呼称", alias_of_idea_id=energy.id,
                  location_id=places["world"].id, start=Stamp(2000))

    called = idea_alias.called(session, [energy.id], places["village"].id, "2100")

    assert called == {energy.id: alias}
    assert idea_alias.name_of(energy, called) == "魔力"
    assert idea_alias.text_of(energy, called) == "住人は魔法の力だと思っている 化学エネルギーとして溜める"


def test_text_of_folds_in_notes_covering_the_time(session, places, energy):
    energy.notes = [IdeaNote(start=Stamp(2050), text="化学反応で生む方法も見つかった")]
    alias = _idea(session, "魔力", "住人は魔法の力だと思っている", kind="呼称", alias_of_idea_id=energy.id,
                  location_id=places["world"].id, start=Stamp(2000),
                  notes=[IdeaNote(start=Stamp(2080), text="教会はこれを禁忌とした")])
    session.commit()

    called = idea_alias.called(session, [energy.id], places["village"].id, "2100")

    assert called == {energy.id: alias}
    assert idea_alias.text_of(energy, called) == (
        "住人は魔法の力だと思っている 化学エネルギーとして溜める")
    assert idea_alias.text_of(energy, called, "2050") == (
        "住人は魔法の力だと思っている 化学エネルギーとして溜める\n化学反応で生む方法も見つかった")
    assert idea_alias.text_of(energy, called, "2100") == (
        "住人は魔法の力だと思っている\n教会はこれを禁忌とした 化学エネルギーとして溜める\n化学反応で生む方法も見つかった")


def test_essence_name_is_used_when_no_alias_matches(session, places, energy):
    _idea(session, "魔力", kind="呼称", alias_of_idea_id=energy.id, location_id=places["world"].id,
          start=Stamp(2200))
    _idea(session, "霊力", kind="呼称", alias_of_idea_id=energy.id, location_id=places["other"].id)

    called = idea_alias.called(session, [energy.id], places["village"].id, "2100")

    assert called == {}
    assert idea_alias.name_of(energy, called) == "エナジー"


def test_empty_columns_of_an_alias_match_any_place_and_time(session, places, energy):
    alias = _idea(session, "力", kind="呼称", alias_of_idea_id=energy.id)

    assert idea_alias.called(session, [energy.id], places["village"].id, "2100") == {energy.id: alias}
    assert idea_alias.called(session, [energy.id]) == {energy.id: alias}


def test_without_place_or_time_only_aliases_with_empty_columns_match(session, places, energy):
    _idea(session, "魔力", kind="呼称", alias_of_idea_id=energy.id, location_id=places["world"].id)
    _idea(session, "旧名", kind="呼称", alias_of_idea_id=energy.id, end=Stamp(2000))

    assert idea_alias.called(session, [energy.id]) == {}


def test_nearer_place_then_later_start_wins(session, places, energy):
    _idea(session, "力", kind="呼称", alias_of_idea_id=energy.id)
    _idea(session, "魔力", kind="呼称", alias_of_idea_id=energy.id, location_id=places["world"].id)
    old = _idea(session, "気", kind="呼称", alias_of_idea_id=energy.id, location_id=places["village"].id,
                start=Stamp(2000))
    new = _idea(session, "霊気", kind="呼称", alias_of_idea_id=energy.id, location_id=places["village"].id,
                start=Stamp(2050))

    assert idea_alias.called(session, [energy.id], places["village"].id, "2100") == {energy.id: new}
    assert idea_alias.called(session, [energy.id], places["village"].id, "2020") == {energy.id: old}


# ---------------------------------------------------------------- 各処理

def test_resolve_hitting_an_alias_returns_the_essence_called_by_the_alias(session, places, energy):
    energy.start = Stamp(1000)
    session.commit()
    alias = _idea(session, "魔力", "住人は魔法の力だと思っている", kind="呼称", alias_of_idea_id=energy.id,
                  location_id=places["world"].id)

    context = idea_context.resolve(session, ["魔力"], places["village"].id, "2100")
    section = idea_context.prompt_section(context.related, context.called)

    assert context.hits == [alias]
    assert context.related == [energy]
    assert context.called == {energy.id: alias}
    assert "- 魔力(技術): 住人は魔法の力だと思っている 化学エネルギーとして溜める" in section
    assert "エナジー" not in section


def test_brief_lists_the_essence_once_by_its_alias(session, places):
    essence = _idea(session, "エナジー", "化学エネルギーとして溜める", location_id=places["world"].id)
    _idea(session, "魔力", kind="呼称", alias_of_idea_id=essence.id, location_id=places["world"].id)

    ideas = _rows.brief(session, places["village"].id, "2100")["ideas"]

    assert [(idea["id"], idea["name"]) for idea in ideas] == [(essence.id, "魔力")]


def test_search_and_resolve_entries_return_the_called_name(session, places, energy):
    alias = _idea(session, "魔力", kind="呼称", alias_of_idea_id=energy.id, location_id=places["world"].id)

    rows = SearchIdeas(["魔力"], place_id=places["village"].id).run()
    resolved = ResolveTerms(["魔力"], places["village"].id).run()

    assert [(row["id"], row["alias_of_idea_id"], row["called"]) for row in rows] == [(alias.id, energy.id, "魔力")]
    assert [(row["id"], row["called"]) for row in resolved["ideas"]] == [(energy.id, "魔力")]


# ---------------------------------------------------------------- 入口の検証

def test_alias_of_an_alias_or_itself_is_rejected(session, energy):
    alias = _idea(session, "魔力", kind="呼称", alias_of_idea_id=energy.id)
    other = _idea(session, "力")

    with pytest.raises(ValueError):
        CommitIdea({"name": "魔の力", "kind": "呼称", "alias_of_idea_id": alias.id}, fact_check=False).run()
    with pytest.raises(ValueError):
        UpdateIdea({"id": other.id, "alias_of_idea_id": other.id}).run()
    with pytest.raises(ValueError):
        UpdateIdea({"id": energy.id, "alias_of_idea_id": other.id}).run()

    UpdateIdea({"id": other.id, "alias_of_idea_id": energy.id}).run()
    session.expire_all()
    assert session.get(Idea, other.id).alias_of_idea_id == energy.id


def test_delete_stops_while_aliases_remain_and_merge_moves_them(session, energy):
    alias = _idea(session, "魔力", kind="呼称", alias_of_idea_id=energy.id)
    target = _idea(session, "エネルギー")
    alias_id, energy_id, target_id = alias.id, energy.id, target.id

    with pytest.raises(ValueError):
        DeleteIdea(energy_id).run()
    MergeIdea(energy_id, target_id).run()

    session.expire_all()
    assert session.get(Idea, energy_id) is None
    assert session.get(Idea, alias_id).alias_of_idea_id == target_id
