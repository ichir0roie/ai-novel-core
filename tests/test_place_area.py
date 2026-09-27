import pytest

from ai.claude_code.interface.randomizer.update_place import UpdatePlace
from db.schema import Location


@pytest.fixture
def continents(session):
    planet = Location(name="星", kind="星", text="", area=100)
    session.add(planet)
    session.flush()
    first = Location(name="大陸", kind="大陸", text="", parent_id=planet.id, area=30)
    second = Location(name="別の大陸", kind="大陸", text="", parent_id=planet.id, area=40)
    session.add_all([first, second])
    session.commit()
    return {"planet": planet.id, "first": first.id, "second": second.id}


def test_update_place_area_fits(session, continents):
    updated = UpdatePlace({"id": continents["first"], "area": 55.5}).run()
    assert updated["area"] == 55.5
    session.expire_all()
    assert float(session.get(Location, continents["first"]).area) == 55.5


def test_update_place_area_over_siblings(continents):
    with pytest.raises(ValueError, match="兄弟"):
        UpdatePlace({"id": continents["first"], "area": 61.0}).run()


def test_update_place_area_over_parent(continents):
    with pytest.raises(ValueError, match="未満でない"):
        UpdatePlace({"id": continents["first"], "area": 100.0}).run()
