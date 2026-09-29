"""claude が CLI から `show()` で呼ぶ、場所(`data_access_logic/location/`)の入口。"""
from data_access_logic.location.commit_place import CommitPlace
from data_access_logic.location.create_random_place import CreateRandomPlace
from data_access_logic.location.delete_place import DeletePlace
from data_access_logic.location.form import LocationCreateForm, LocationUpdateForm
from data_access_logic.location.list_neighbors import ListNeighbors
from data_access_logic.location.list_places import ListPlaces
from data_access_logic.location.update_place import UpdatePlace

_POLYGON = {"type": "Polygon", "coordinates": [[[135.0, 34.0], [135.2, 34.0], [135.2, 34.2], [135.0, 34.0]]]}


def test_commit_place(shown, world):
    result = shown(CommitPlace(LocationCreateForm(
        name="テスト港", kind="港", text="テスト用の港", active_random_generation=True, parent_id=world.planet_id,
        location_world=1, location_planet=world.planet_id, location_longitude=135.1, location_latitude=34.1,
        location_altitude=2, polygon=_POLYGON, area=50, environment="海辺", sample_region="北欧",
        sample_culture="漁労", sample_era="近世", start="1200/01/01", end="2000/01/01")))

    assert (result["name"], result["kind"], result["text"]) == ("テスト港", "港", "テスト用の港")
    assert result["active_random_generation"] is True
    assert (result["parent_id"], result["location_planet"]) == (world.planet_id, world.planet_id)
    assert (result["location_longitude"], result["location_latitude"], result["location_altitude"]) == (135.1, 34.1, 2)
    assert result["polygon"] == _POLYGON
    assert (result["area"], result["environment"]) == (50, "海辺")
    assert (result["sample_region"], result["sample_culture"], result["sample_era"]) == ("北欧", "漁労", "近世")
    assert (result["start"], result["end"]) == ("1200/01/01 00:00:00", "2000/01/01 00:00:00")


def test_create_random_place(shown):
    result = shown(CreateRandomPlace(name="乱数の場所", kind="町", text="乱数で作った場所"))

    assert (result["name"], result["kind"], result["text"]) == ("乱数の場所", "町", "乱数で作った場所")
    LocationCreateForm.model_validate(result)


def test_delete_place(shown, world):
    result = shown(DeletePlace(place_id=world.neighbor_id))

    assert result == {"id": world.neighbor_id, "name": "テスト村", "kind": "村"}


def test_list_neighbors(shown, world):
    result = shown(ListNeighbors(place_id=world.place_id, kind="村", limit=3))

    assert result["place"]["id"] == world.place_id
    assert result["planet"]["id"] == world.planet_id
    assert [neighbor["id"] for neighbor in result["neighbors"]] == [world.neighbor_id]
    assert result["neighbors"][0]["altitude_diff_m"] == 250


def test_list_places(shown, world):
    result = shown(ListPlaces(kind="都市"))

    assert world.place_id in [place["id"] for place in result]
    assert {place["kind"] for place in result} == {"都市"}


def test_update_place(shown, world):
    result = shown(UpdatePlace(LocationUpdateForm(
        id=world.neighbor_id, name="テスト山村", kind="山村", text="山あいの村", active_random_generation=True,
        parent_id=world.planet_id, location_world=2, location_planet=world.planet_id, location_longitude=136.2,
        location_latitude=35.7, location_altitude=600, polygon=_POLYGON, area=200, environment="高地",
        sample_region="アルプス", sample_culture="牧畜", sample_era="中世", start="1160/01/01", end="2800/01/01")))

    assert (result["name"], result["kind"], result["text"]) == ("テスト山村", "山村", "山あいの村")
    assert result["active_random_generation"] is True
    assert (result["location_world"], result["location_longitude"], result["location_latitude"]) == (2, 136.2, 35.7)
    assert (result["location_altitude"], result["area"]) == (600, 200)
    assert result["polygon"] == _POLYGON
    assert (result["environment"], result["sample_region"]) == ("高地", "アルプス")
    assert (result["sample_culture"], result["sample_era"]) == ("牧畜", "中世")
    assert (result["start"], result["end"]) == ("1160/01/01 00:00:00", "2800/01/01 00:00:00")
