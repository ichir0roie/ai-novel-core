import pytest

from ai.claude_code.interface.story import _rows
from data_access_logic.query import common_query
from db.schema import Idea, Location
from db.stamp import Stamp


@pytest.fixture
def places(session):
    world = Location(name="世界線", kind="世界線", text="")
    session.add(world)
    session.flush()
    planet = Location(name="星", kind="星", parent_id=world.id, text="")
    session.add(planet)
    session.flush()
    country = Location(name="国", kind="国", parent_id=planet.id, text="")
    session.add(country)
    session.flush()
    return {"world": world.id, "planet": planet.id, "country": country.id}


def add_idea(session, name, **columns):
    record = Idea(name=name, kind="概念", text="", **columns)
    session.add(record)
    session.flush()
    return record.id


def brief_names(session, place_id, when="0001/01/01"):
    return sorted(idea["name"] for idea in _rows.brief(session, place_id, when)["ideas"])


def test_scope_runs_from_the_place_up_to_the_top(session, places):
    assert common_query.idea_scope_ids(session, places["country"]) == [
        places["country"], places["planet"], places["world"]]
    assert common_query.idea_scope_ids(session, places["planet"]) == [places["planet"], places["world"]]


def test_ideas_of_the_place_and_above_reach_the_brief(session, places):
    add_idea(session, "世界線のアイデア", location_id=places["world"])
    add_idea(session, "星のアイデア", location_id=places["planet"])
    add_idea(session, "国のアイデア", location_id=places["country"])
    session.commit()

    assert brief_names(session, places["country"]) == ["世界線のアイデア", "国のアイデア", "星のアイデア"]
    assert brief_names(session, places["planet"]) == ["世界線のアイデア", "星のアイデア"]


def test_idea_without_location_is_left_out(session, places):
    add_idea(session, "掛かる先の無いアイデア")
    session.commit()

    assert brief_names(session, places["planet"]) == []


def test_idea_of_another_branch_is_left_out(session, places):
    other = Location(name="別の星", kind="星", parent_id=places["world"], text="")
    session.add(other)
    session.flush()
    add_idea(session, "別の星のアイデア", location_id=other.id)
    session.commit()

    assert brief_names(session, places["planet"]) == []


def test_idea_counts_from_start_until_before_end(session, places):
    add_idea(session, "時代のアイデア", location_id=places["world"], start=Stamp(100), end=Stamp(200))
    session.commit()

    assert brief_names(session, places["planet"], "99/12/31") == []
    assert brief_names(session, places["planet"], "100/01/01") == ["時代のアイデア"]
    assert brief_names(session, places["planet"], "199/12/31") == ["時代のアイデア"]
    assert brief_names(session, places["planet"], "200/01/01") == []
