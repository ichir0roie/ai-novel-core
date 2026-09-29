import json

import pytest

from data_access_logic.location.commit_place import CommitPlace
from data_access_logic.location.list_neighbors import ListNeighbors
from data_access_logic.location.update_place import UpdatePlace
from data_access_logic.map.collect import planet_maps
from data_access_logic.map.layout import fit_frame
from db.polygon import outer_ring, parse_polygon, polygon_center
from db.schema import Location

TRIANGLE = [[10, 20], [30, 20], [30, 40]]
CLOSED = {"type": "Polygon", "coordinates": [[[10.0, 20.0], [30.0, 20.0], [30.0, 40.0], [10.0, 20.0]]]}


def test_parse_polygon_closes_ring_and_normalizes():
    assert parse_polygon(TRIANGLE) == CLOSED
    assert parse_polygon([TRIANGLE]) == CLOSED
    assert parse_polygon(CLOSED) == CLOSED
    assert parse_polygon(json.dumps(CLOSED)) == CLOSED
    assert parse_polygon(None) is None and parse_polygon("") is None
    with_hole = parse_polygon([[[0, 0], [40, 0], [40, 40], [0, 40]], [[10, 10], [20, 10], [20, 20]]])
    assert len(with_hole["coordinates"]) == 2 and len(with_hole["coordinates"][1]) == 4


@pytest.mark.parametrize("bad", [
    [[10, 20], [30, 20]],                    # 三点未満
    [[10, 20, 5], [30, 20], [30, 40]],       # 三つ組
    [[200, 20], [30, 20], [30, 40]],         # 経度の範囲外
    {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
    {"type": "Polygon", "coordinates": []},
    "not json", 42,
])
def test_parse_polygon_rejects(bad):
    with pytest.raises(ValueError):
        parse_polygon(bad)


def test_outer_ring_and_center():
    assert outer_ring(CLOSED) == [[10.0, 20.0], [30.0, 20.0], [30.0, 40.0]]
    assert polygon_center(CLOSED) == pytest.approx((70 / 3, 80 / 3))


def test_commit_and_update_place_store_polygon(session):
    created = CommitPlace({"name": "国", "kind": "国", "text": "", "polygon": TRIANGLE}).run()
    assert created["polygon"] == CLOSED
    assert session.get(Location, created["id"]).polygon == CLOSED

    updated = UpdatePlace({"id": created["id"], "polygon": None}).run()
    assert updated["polygon"] is None
    session.expire_all()
    assert session.get(Location, created["id"]).polygon is None
    assert session.query(Location).filter(Location.polygon.is_(None)).count() == 1

    with pytest.raises(ValueError, match="三つ以上"):
        UpdatePlace({"id": created["id"], "polygon": [[0, 0], [1, 1]]}).run()


@pytest.fixture
def outlined(session):
    planet = Location(name="星", kind="星", text="", area=510_072_000)
    session.add(planet)
    session.flush()
    continent = Location(name="大陸", kind="大陸", text="", parent_id=planet.id, location_planet=planet.id,
                         polygon=[[-20, -10], [60, -10], [60, 50], [-20, 50]])
    session.add(continent)
    session.flush()
    country = Location(name="国", kind="国", text="", parent_id=continent.id, location_planet=planet.id,
                       location_longitude=20, location_latitude=20, polygon=TRIANGLE)
    town = Location(name="町", kind="町", text="", parent_id=continent.id, location_planet=planet.id,
                    location_longitude=5, location_latitude=5)
    session.add_all([country, town])
    session.commit()
    return {"planet": planet.id, "continent": continent.id, "country": country.id, "town": town.id}


def test_collect_separates_points_and_shapes(session, outlined):
    [entry] = planet_maps(session)
    assert [p.name for p in entry.points] == ["国", "町"]
    assert [p.name for p in entry.shapes] == ["大陸", "国"]
    assert entry.shapes[0].lon is None and entry.shapes[0].polygon is not None
    assert entry.shapes[0].polygon["type"] == "Polygon"
    assert entry.points[1].polygon is None

    frame = fit_frame(entry.points, entry.shapes)
    assert (frame.lon_min, frame.lon_max, frame.lat_min, frame.lat_max) == (-30, 70, -20, 60)


def test_list_neighbors_ignores_shape_only_places(outlined):
    result = ListNeighbors(outlined["town"]).run()
    assert [n["name"] for n in result["neighbors"]] == ["国"]
    assert result["neighbors"][0]["polygon"] == CLOSED
