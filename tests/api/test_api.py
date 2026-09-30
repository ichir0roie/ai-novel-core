"""GUI の API(`gui/api/app.py`)。エンドポイントごとに、なるべく多くの値を渡す一件を通す。"""
import os
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from gui.api.app import app
from tool.test import TEST_DB_PATH


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def in_claude_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """`claude` を叩く入口は Claude Code の環境(`CLAUDECODE=1`)でだけ通る。AI はモックに差し替えてある。"""
    monkeypatch.setenv("CLAUDECODE", "1")


def _finished(client: TestClient, job_id: str) -> dict:
    """裏の job が終わるまで待つ(モックの AI なので数秒で終わる)。"""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} が終わらない")


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"world_dir": os.environ["DEM_WORLD_DIR"], "db_path": TEST_DB_PATH}


def test_tables(client, world, in_claude_code):
    response = client.get("/api/tables")

    assert response.status_code == 200
    body = response.json()
    assert body["claude_available"] is True
    tables = {table["name"]: table for table in body["tables"]}
    assert set(tables) == {"story", "episode", "character", "character_relation", "event", "location", "idea",
                           "meme", "oracle"}
    assert [generator["key"] for generator in tables["episode"]["generators"]] == ["frame", "plot", "episode", "revise"]
    assert {child["name"] for child in tables["character"]["child_lists"]} == {"parameters", "locations", "histories"}


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
        "name": "API の人", "text": "API から足した人物", "kind": "人物", "confirmed": "未確認", "main_character": True,
        "event_seeded": True, "meme_seeded": True, "location_id": world.location_id, "start": "1181/02/03",
        "end": "1255/06/07",
        "parameters": [{"start": "1181/02/03", "end": "1255/06/07", "family_name": "東雲", "sex": "女", "height": 162.5,
                        "build": "中背", "first_person": "わたくし", "second_person": "貴方", "third_person": "彼の方",
                        "tone": "上品", "dialect": "都言葉", "sincerity": "高", "curiosity": "必", "proactivity": "並",
                        "cooperativeness": "低", "sociability": "無", "emotional_expression": "並",
                        "self_esteem": "高", "self_efficacy": "並", "stress_resilience": "低",
                        "flexibility_of_values": "高", "sensitivity": "並", "imagination": "高"}],
        "histories": [{"start": "1200/01/01", "end": "1210/01/01", "description": "都の役所に勤める"}]})

    assert response.status_code == 201
    body = response.json()
    record = body["record"]
    assert (record["name"], record["text"], record["confirmed"]) == ("API の人", "API から足した人物", "未確認")
    assert (record["start"], record["end"]) == ("1181/02/03 00:00:00", "1255/06/07 00:00:00")
    assert record["parameters"][0]["curiosity"] == "必"
    assert record["locations"][0]["location_id"] == world.location_id
    assert record["histories"][0]["description"] == "都の役所に勤める"
    assert body["label"] == "API の人"


def test_generate_record(client, world, in_claude_code, mock_ai):
    response = client.post("/api/tables/episode/generate/episode", json={
        "draft": {"story_id": world.story_id, "title": "API の話", "plot_text": "API から書く話",
                  "start": "1200/04/03 09:00:00", "end": "1200/04/03 12:00:00",
                  "viewpoint_character_id": world.character_ids[1], "location_id": world.location_id,
                  "character_ids": world.character_ids},
        "args": {"model": "claude-haiku-4-5", "effort": "low"}})

    assert response.status_code == 202
    job = _finished(client, response.json()["id"])
    assert job["status"] == "done", job["error"]
    assert job["entrance"] == "episode.generate_episode.GenerateEpisode"
    result = job["result"]
    assert (result["story_id"], result["plot_text"]) == (world.story_id, "API から書く話")
    assert result["viewpoint_character_id"] == world.character_ids[1]
    assert result["character_ids"] == world.character_ids
    assert result["main_text"]


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
        "confirmed": "非承認", "parent_event_id": world.event_id, "location_id": world.neighbor_id,
        "start": "1200/04/01 16:30:00", "end": "1200/04/01 18:00:00", "event_seeded": False, "meme_seeded": False,
        "character_ids": world.character_ids})

    assert response.status_code == 200
    record = response.json()["record"]
    assert (record["name"], record["text"], record["confirmed"]) == ("API で直した取引", "API で直した", "非承認")
    assert (record["time"], record["end"]) == ("1200/04/01 16:30:00", "1200/04/01 18:00:00")
    assert (record["hidden"], record["parent_event_id"], record["location_id"]) == (True, world.event_id,
                                                                                    world.neighbor_id)
    assert (record["event_seeded"], record["meme_seeded"]) == (False, False)
    assert record["character_ids"] == world.character_ids


def test_review_summary(client, world):
    response = client.get("/api/review")

    assert response.status_code == 200
    tables = {table["table"]: table for table in response.json()["tables"]}
    assert set(tables) == {"character", "event", "idea", "meme"}
    assert tables["idea"]["pending"] >= 1
    assert tables["meme"]["pending"] >= 1


def test_review_next(client, world):
    response = client.get("/api/review/idea/next", params={"after": world.idea_id})

    assert response.status_code == 200
    body = response.json()
    assert body["record"]["id"] == world.child_idea_id
    assert body["label"] == "テスト魔導炉"
    assert body["remaining"] >= 1
    assert body["labels"]["parent_idea_id"] == {str(world.idea_id): "テスト魔導"}


def test_review_decide(client, world):
    response = client.post(f"/api/review/idea/{world.child_idea_id}", json={
        "decision": "承認",
        "changes": {"name": "承認した魔導炉", "kind": "装置", "text": "直して承認した", "location_id": world.neighbor_id,
                    "start": "1150/01/01", "end": "1250/01/01", "meme_seeded": False,
                    "recognitions": [{"location_id": world.neighbor_id, "start": "1160/01/01", "end": None,
                                      "name": "炉", "detail": "村での呼び名"}]}})

    assert response.status_code == 200
    record = response.json()["record"]
    assert (record["confirmed"], record["name"], record["kind"]) == ("承認", "承認した魔導炉", "装置")
    assert (record["text"], record["location_id"]) == ("直して承認した", world.neighbor_id)
    assert (record["start"], record["end"]) == ("1150/01/01 00:00:00", "1250/01/01 00:00:00")
    assert [recognition["name"] for recognition in record["recognitions"]] == ["炉"]


def test_list_entrances(client, in_claude_code):
    response = client.get("/api/interface")

    assert response.status_code == 200
    body = response.json()
    assert body["claude_available"] is True
    entrances = {entrance["id"]: entrance for entrance in body["entrances"]}
    start_story = entrances["story.start_story.StartStory"]
    assert (start_story["claude"], start_story["writes"]) == (False, False)
    assert [param["name"] for param in start_story["params"]] == [
        "story_id", "time", "episodes", "count", "reach", "levels", "skip_sync"]
    commit_event = entrances["event.commit_event.CommitEvent"]
    assert (commit_event["claude"], commit_event["writes"]) == (True, True)


def test_run_entrance(client, world):
    response = client.post("/api/interface/story.start_story.StartStory", json={
        "args": {"story_id": world.story_id, "time": "1200/04/02", "episodes": 5, "count": 3, "reach": 30,
                 "levels": 2, "skip_sync": True},
        "background": False})

    assert response.status_code == 200
    body = response.json()
    assert body["entrance"] == "story.start_story.StartStory"
    result = body["result"]
    assert (result["stopped"], result["time"]) == (False, "1200/04/02 23:59:59")
    assert [episode["id"] for episode in result["episodes"]] == [world.episode_id]
    assert result["cast"] is not None
    assert result["brief"] is not None


def test_list_jobs(client, world):
    submitted = client.post("/api/interface/episode.read_episodes.ReadEpisodes", json={
        "args": {"story_id": world.story_id, "count": 3, "before": "1200/12/31", "text": False}, "background": True})
    assert submitted.status_code == 202
    job_id = submitted.json()["id"]
    _finished(client, job_id)

    response = client.get("/api/jobs")

    assert response.status_code == 200
    jobs = {job["id"]: job for job in response.json()["jobs"]}
    assert jobs[job_id]["entrance"] == "episode.read_episodes.ReadEpisodes"
    assert jobs[job_id]["status"] == "done"


def test_get_job(client, world):
    submitted = client.post("/api/interface/event.read_events.ReadEvents", json={
        "args": {"location_id": world.location_id, "limit": 5, "until": "1200/12/31"}, "background": True})
    assert submitted.status_code == 202

    job = _finished(client, submitted.json()["id"])

    assert job["status"] == "done", job["error"]
    assert job["args"] == {"location_id": world.location_id, "limit": 5, "until": "1200/12/31"}
    assert job["started_at"] is not None and job["finished_at"] is not None
    assert {world.event_id, world.child_event_id} <= {event["id"] for event in job["result"]}


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
