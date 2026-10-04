"""GUI の API(`gui/api/app.py`)。エンドポイントごとに、なるべく多くの値を渡す一件を通す。"""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from gui.api.app import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    health = response.json()
    assert health["dialect"] == "postgresql"


def test_tables(client, world):
    response = client.get("/api/tables")

    assert response.status_code == 200
    body = response.json()
    tables = {table["name"]: table for table in body["tables"]}
    assert set(tables) == {"story", "episode", "character", "character_relation", "event", "location", "idea",
                           "meme", "oracle", "style_preference"}
    assert {child["name"] for child in tables["character"]["child_lists"]} == {"parameters", "locations", "histories", "knowers"}


def test_list_records(client, world):
    response = client.get("/api/tables/episode/records", params={
        "q": "テスト第一話", "limit": 10, "offset": 0, "sort": "start", "order": "desc",
        "story_id": world.story_id, "synced": "true", "location_id": world.location_id})

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (1, 10, 0)
    item = body["items"][0]
    assert item["id"] == world.episode_id
    # 本文の列(話はプロット・本文の順)は外し、空でない最初の列の頭を preview に出す
    assert item["preview"] == "市で出会う"
    assert "plot_text" not in item and "main_text" not in item and "summary_text" not in item
    assert body["labels"]["story_id"] == {str(world.story_id): "テスト作品"}
    assert set(body["labels"]["character_ids"]) == {str(id_) for id_ in world.character_ids}


def test_list_options(client, world):
    response = client.get("/api/tables/idea/options", params={
        "q": "テスト魔導", "limit": 5, "ids": [world.idea_id, world.child_idea_id]})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [world.idea_id, world.child_idea_id]
    assert [item["parent_id"] for item in items] == [None, world.idea_id]


def test_create_record(client, world):
    response = client.post("/api/tables/character/records", json={
        "name": "API の人", "text": "API から足した人物", "kind": "人物", "main_character": True,
        "event_seeded": True, "location_id": world.location_id, "start": "1181/02/03",
        "end": "1255/06/07",
        "parameters": [{"start": "1181/02/03", "family_name": "東雲", "sex": "女", "height": 162.5,
                        "build": "中背", "first_person": "わたくし", "second_person": "貴方", "third_person": "彼の方",
                        "tone": "上品", "dialect": "都言葉", "sincerity": "高", "curiosity": "必", "proactivity": "並",
                        "cooperativeness": "低", "sociability": "無", "emotional_expression": "並",
                        "self_esteem": "高", "self_efficacy": "並", "stress_resilience": "低",
                        "flexibility_of_values": "高", "sensitivity": "並", "imagination": "高"}],
        "histories": [{"start": 1200, "description": "都の役所に勤める"}]})

    assert response.status_code == 201
    body = response.json()
    record = body["record"]
    assert (record["name"], record["text"]) == ("API の人", "API から足した人物")
    assert (record["start"], record["end"]) == ("1181/02/03 00:00:00", "1255/06/07 00:00:00")
    assert record["parameters"][0]["curiosity"] == "必"
    assert record["locations"][0]["location_id"] == world.location_id
    assert record["histories"][0]["description"] == "都の役所に勤める"
    assert body["label"] == "API の人"


def test_get_record(client, world):
    response = client.get(f"/api/tables/episode/records/{world.episode_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["record"]["id"] == world.episode_id
    assert body["record"]["character_ids"] == world.character_ids
    assert body["label"] == "テスト第一話"
    assert body["labels"]["viewpoint_character_id"] == {str(world.character_ids[0]): "テスト太郎"}
    # 話の時期・場所に重なる出来事と、同じ場所の他の作品
    event_ids = [item["id"] for item in body["related"]["context"]["event"]["items"]]
    assert world.event_id in event_ids


def test_update_record(client, world):
    response = client.patch(f"/api/tables/event/records/{world.child_event_id}", json={
        "name": "API で直した取引", "time": "1200/04/01 16:30:00", "text": "API で直した", "hidden": True,
        "parent_event_id": world.event_id, "location_id": world.neighbor_id,
        "start": "1200/04/01 16:30:00", "end": "1200/04/01 18:00:00", "event_seeded": False, "meme_seeded": False,
        "character_ids": world.character_ids})

    assert response.status_code == 200
    record = response.json()["record"]
    assert (record["name"], record["text"]) == ("API で直した取引", "API で直した")
    assert (record["time"], record["end"]) == ("1200/04/01 16:30:00", "1200/04/01 18:00:00")
    assert (record["hidden"], record["parent_event_id"], record["location_id"]) == (True, world.event_id,
                                                                                    world.neighbor_id)
    assert (record["event_seeded"], record["meme_seeded"]) == (False, False)
    assert record["character_ids"] == world.character_ids


def test_list_entrances(client):
    response = client.get("/api/interface")

    assert response.status_code == 200
    entrances = {entrance["id"]: entrance for entrance in response.json()["entrances"]}
    start_story = entrances["story.start_story.StartStory"]
    assert start_story["writes"] is False
    assert [param["name"] for param in start_story["params"]] == [
        "story_id", "time", "episodes", "count", "reach", "levels", "skip_sync"]
    assert entrances["episode.delete_episode.DeleteEpisode"]["writes"] is True
    # claude を叩く入口は出さない
    assert "event.commit_event.CommitEvent" not in entrances


def test_run_entrance(client, world):
    response = client.post("/api/interface/story.start_story.StartStory", json={
        "args": {"story_id": world.story_id, "time": "1200/04/02", "episodes": 5, "count": 3, "reach": 30,
                 "levels": 2, "skip_sync": True}})

    assert response.status_code == 200
    body = response.json()
    assert body["entrance"] == "story.start_story.StartStory"
    result = body["result"]
    assert (result["stopped"], result["time"]) == (False, "1200/04/02 23:59:59")
    assert [episode["id"] for episode in result["episodes"]] == [world.episode_id]
    assert result["cast"] is not None
    assert result["brief"] is not None


def test_run_claude_entrance(client, world):
    response = client.post("/api/interface/event.commit_event.CommitEvent", json={"args": {}})

    assert response.status_code == 403


def test_maps(client, world):
    response = client.get("/api/maps")

    assert response.status_code == 200
    body = response.json()
    planet_map = next(planet_map for planet_map in body["planets"] if planet_map["planet"]["id"] == world.planet_id)
    assert {point["id"] for point in planet_map["points"]} == {world.location_id, world.neighbor_id}
    assert [shape["id"] for shape in planet_map["shapes"]] == [world.neighbor_id]
    assert body["categories"]
    assert body["bearings"]


def test_map_svg(client, world):
    response = client.get(f"/api/maps/{world.planet_id}.svg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert "テスト都" in response.text
    assert "テスト村" in response.text


def test_relations(client, world):
    response = client.get("/api/relations")

    assert response.status_code == 200
    body = response.json()
    characters = {character["id"]: character for character in body["characters"]}
    assert characters[world.character_ids[0]]["sex"] == "男"
    assert characters[world.character_ids[0]]["start"] == 1170
    relation = next(relation for relation in body["relations"] if relation["id"] == world.relation_id)
    assert (relation["relation"], relation["text"], relation["start"]) == ("幼なじみ", "同じ通りで育った", 1175)
    assert body["colors"]


def test_character_locations(client, world):
    response = client.get("/api/character_locations")

    assert response.status_code == 200
    locations = response.json()["locations"]
    assert all(locations[str(character_id)] == world.location_id for character_id in world.character_ids)


def test_batch(client, world):
    response = client.post("/api/batch", json={"paths": [
        f"/api/tables/episode/records/{world.episode_id}",
        f"/api/tables/idea/options?q=テスト魔導&ids={world.idea_id}",
        "/api/tables/no_such_table/records"]})

    assert response.status_code == 200
    record, options, unknown = response.json()["responses"]
    assert (record["status"], record["body"]["record"]["id"]) == (200, world.episode_id)
    assert (options["status"], [item["id"] for item in options["body"]["items"]]) == (200, [world.idea_id])
    assert unknown["status"] == 404 and "detail" in unknown["body"]


def test_batch_rejects_other_paths(client):
    for path in ["/api/batch", "https://example.com/api/tables", "/docs"]:
        response = client.post("/api/batch", json={"paths": [path]})

        assert response.status_code == 400, path
