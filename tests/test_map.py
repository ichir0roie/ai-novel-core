
import pytest

from ai.claude_code.interface.world.list_neighbors import ListNeighbors
from data_access_logic.query.common_query import NotFoundError
from db.schema import Location
from tool.map.category import category_of
from tool.map.geometry import (
    angular_distance_deg, bearing_deg, bearing_name, distance_km, planet_radius_km,
)
from tool.map.layout import fit_frame, place_labels, text_width

EARTH_AREA = 510_072_000
TOKYO = (139.69, 35.69)
LONDON = (-0.13, 51.51)


def test_planet_radius_from_area():
    assert planet_radius_km(EARTH_AREA) == pytest.approx(6371, abs=2)
    assert planet_radius_km(None) is None
    assert planet_radius_km(0) is None


def test_great_circle_distance_and_bearing():
    radius = planet_radius_km(EARTH_AREA)
    km = distance_km(radius, *TOKYO, *LONDON)
    assert km == pytest.approx(9560, rel=0.01)
    assert distance_km(None, *TOKYO, *LONDON) is None
    assert angular_distance_deg(0, 0, 0, 0) == 0
    assert bearing_name(bearing_deg(0, 0, 0, 10)) == "北"
    assert bearing_name(bearing_deg(0, 0, 10, 0)) == "東"
    assert bearing_name(bearing_deg(0, 0, 0, -10)) == "南"
    assert bearing_name(bearing_deg(0, 0, -10, 0)) == "西"
    assert bearing_name(bearing_deg(0, 0, 10, 10)) == "北東"


def test_fit_frame_pads_and_snaps_to_grid():
    frame = fit_frame([{"lon": -12, "lat": 36}, {"lon": 125, "lat": -26}])
    assert (frame.lon_min, frame.lon_max, frame.lat_min, frame.lat_max) == (-30, 140, -40, 50)
    assert frame.x(frame.lon_min) == frame.left and frame.y(frame.lat_max) == frame.top
    whole = fit_frame([{"lon": -179, "lat": 89}, {"lon": 179, "lat": -89}])
    assert (whole.lon_min, whole.lon_max, whole.lat_min, whole.lat_max) == (-180, 180, -90, 90)


def test_category_of_kind():
    assert category_of("大陸") == category_of("世界") == "大陸"
    assert category_of("国") == "国"
    assert category_of("都市") == category_of("町") == category_of("村") == "都市"
    assert category_of("森") == category_of("火山") == category_of(None) == "自然"


def test_place_labels_avoid_each_other():
    items = [(100, 100, "ヴェルム聖王国"), (104, 102, "エンピレオ"), (108, 104, "夏の宮廷")]
    boxes = []
    for (x, y, anchor), (_, _, text) in zip(place_labels(items), items):
        w = text_width(text)
        left = x - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        boxes.append((left, y - 13, left + w, y))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


@pytest.fixture
def star(session):
    line = Location(name="世界線", kind="世界線", text="")
    session.add(line)
    session.flush()
    planet = Location(name="星", kind="星", text="", parent_id=line.id, area=EARTH_AREA)
    session.add(planet)
    session.flush()
    continent = Location(name="大陸", kind="大陸", text="", parent_id=planet.id, location_planet=planet.id)
    sky = Location(name="天上", kind="世界", text="", parent_id=planet.id, location_planet=planet.id)
    session.add_all([continent, sky])
    session.flush()

    def country(name, parent, lon, lat, alt, kind="国"):
        row = Location(name=name, kind=kind, text="", parent_id=parent.id, location_planet=planet.id,
                       location_longitude=lon, location_latitude=lat, location_altitude=alt)
        session.add(row)
        return row

    origin = country("東京", continent, *TOKYO, 40)
    london = country("ロンドン", continent, *LONDON, 11)
    north = country("北の町", continent, TOKYO[0], TOKYO[1] + 5, 100, kind="町")
    above = country("空の都", sky, *TOKYO, 20040)
    session.commit()
    return {"planet": planet.id, "origin": origin.id, "london": london.id,
            "north": north.id, "above": above.id, "continent": continent.id}


def test_list_neighbors_sorted_by_distance(star):
    result = ListNeighbors(star["origin"]).run()

    assert result["planet"]["radius_km"] == pytest.approx(6371, abs=2)
    assert result["place"]["id"] == star["origin"]
    names = [n["name"] for n in result["neighbors"]]
    assert names == ["空の都", "北の町", "ロンドン"]

    above, north, london = result["neighbors"]
    assert above["bearing"] == "同じ経緯度" and above["distance_km"] == 0
    assert above["altitude_diff_m"] == 20000
    assert above["summary"] == "空の都(国・天上): 同じ経緯度、上へ 20,000 m"
    assert north["bearing"] == "北" and north["distance_km"] == pytest.approx(556, abs=2)
    assert north["summary"] == "北の町(町・大陸): 北 約560 km、上へ 60 m"
    assert london["distance_km"] == pytest.approx(9560, rel=0.01)
    assert london["summary"].startswith("ロンドン(国・大陸): 北北西 約9,5")


def test_list_neighbors_kind_and_limit(star):
    rows = ListNeighbors(star["origin"], kind="国").run()["neighbors"]
    assert [n["name"] for n in rows] == ["空の都", "ロンドン"]
    rows = ListNeighbors(star["origin"], limit=1).run()["neighbors"]
    assert [n["name"] for n in rows] == ["空の都"]


def test_list_neighbors_rejects_place_without_coordinates(star):
    with pytest.raises(ValueError, match="経緯度を持たない"):
        ListNeighbors(star["continent"]).run()
    with pytest.raises(NotFoundError):
        ListNeighbors(999999).run()
