"""claude が CLI から `show()` で呼ぶ、場所(`data_access_logic/location/`)の入口。"""
from data_access_logic.location.commit_location import CommitLocation
from data_access_logic.location.create_random_location import CreateRandomLocation
from data_access_logic.location.delete_location import DeleteLocation
from data_access_logic.location.form import LocationCreateForm, LocationUpdateForm
from data_access_logic.location.list_neighbors import ListNeighbors
from data_access_logic.location.list_locations import ListLocations
from data_access_logic.episode.read_episode_brief import ReadEpisodeBrief
from data_access_logic.episode_session.read_stage import ReadStage
from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.location.update_location import UpdateLocation

_POLYGON = {"type": "Polygon", "coordinates": [[[135.0, 34.0], [135.2, 34.0], [135.2, 34.2], [135.0, 34.0]]]}


def test_commit_location(shown, world):
    result = shown(CommitLocation(LocationCreateForm(
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


def test_create_random_location(shown):
    result = shown(CreateRandomLocation(name="乱数の場所", kind="町", text="乱数で作った場所"))

    assert (result["name"], result["kind"], result["text"]) == ("乱数の場所", "町", "乱数で作った場所")
    LocationCreateForm.model_validate(result)


def test_delete_location(shown, world):
    result = shown(DeleteLocation(location_id=world.neighbor_id))

    assert result == {"id": world.neighbor_id, "name": "テスト村", "kind": "村"}


def test_list_neighbors(shown, world):
    result = shown(ListNeighbors(location_id=world.location_id, kind="村", limit=3))

    assert result["location"]["id"] == world.location_id
    assert result["planet"]["id"] == world.planet_id
    assert [neighbor["id"] for neighbor in result["neighbors"]] == [world.neighbor_id]
    assert result["neighbors"][0]["altitude_diff_m"] == 250


def test_list_locations(shown, world):
    result = shown(ListLocations(kind="都市"))

    assert world.location_id in [location["id"] for location in result]
    assert {location["kind"] for location in result} == {"都市"}


def test_update_location(shown, world):
    result = shown(UpdateLocation(LocationUpdateForm(
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


def test_location_histories(shown, world):
    created = shown(CommitLocation(LocationCreateForm(
        name="テスト関所", kind="関所", parent_id=world.planet_id,
        histories=[LocationHistoryRow(start=1180, description="関所が置かれる")])))
    assert created["histories"] == [{"start": 1180, "description": "関所が置かれる"}]

    # 来歴は配列でまるごと置き換え、渡さなければ触らない
    shown(UpdateLocation(LocationUpdateForm(id=created["id"], histories=[
        LocationHistoryRow(start=1180, description="関所が置かれる"), LocationHistoryRow(description="年の決まっていない構想")])))
    result = shown(UpdateLocation(LocationUpdateForm(id=created["id"], text="山あいの関所")))

    assert result["text"] == "山あいの関所"
    assert sorted(result["histories"], key=str) == sorted(
        [{"start": 1180, "description": "関所が置かれる"}, {"start": None, "description": "年の決まっていない構想"}], key=str)


def test_episode_materials_have_location_text_and_histories(shown, world):
    shown(UpdateLocation(LocationUpdateForm(id=world.location_id, histories=[
        LocationHistoryRow(start=1250, description="先に起きること"),
        LocationHistoryRow(start=1190, description="市が立つ"),
        LocationHistoryRow(description="年未定の構想")])))
    expected = ["1190年: 市が立つ"]

    brief = shown(ReadEpisodeBrief(episode_id=world.episode_id))
    # 話の時刻(1200 年)の年までに起きた来歴だけを、場所の説明と一緒に渡す
    place = brief["この話"]["場所(広い順)"][-1]
    assert place["場所id"] == world.location_id
    assert place["説明"]
    assert place["来歴(古い順)"] == expected

    stage = shown(ReadStage(episode_id=world.episode_id))
    assert stage["場所の来歴(古い順)"] == expected
