"""GUI の「AI で作成」の API(`/api/tables/{table}/generate/{key}`)。claude を叩く入口を裏の job で回すこと。"""
import time

import pytest
from fastapi.testclient import TestClient

from gui.api import app as app_module, interface


@pytest.fixture
def client():
    return TestClient(app_module.app)


def _wait(client, job_id, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job が終わらない")


def test_tables_meta_lists_the_generators(client, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    body = client.get("/api/tables").json()
    tables = {table["name"]: table for table in body["tables"]}

    assert body["claude_available"] is False
    assert [g["key"] for g in tables["character"]["generators"]] == ["ai", "complete"]
    character = {g["key"]: g for g in tables["character"]["generators"]}
    assert character["ai"]["entrance"] == "randomizer.generate_character.GenerateCharacter"
    assert [p["key"] for p in character["ai"]["params"]] == ["time"]
    assert character["ai"]["mode"] == "create"
    assert character["complete"]["mode"] == "edit" and character["complete"]["when_empty"] == "text"
    assert [g["key"] for g in tables["event"]["generators"]] == ["ai", "complete"]
    event = {g["key"]: g for g in tables["event"]["generators"]}
    assert event["complete"]["mode"] == "edit" and event["complete"]["when_empty"] == "text"
    episode = {g["key"]: g for g in tables["episode"]["generators"]}
    assert episode["frame"]["mode"] == "create" and episode["episode"]["mode"] == "both" and episode["episode"]["when_empty"] == "text"
    assert {p["key"] for p in episode["episode"]["params"]} == {"character_ids", "previous_episode_ids", "model", "effort"}
    assert tables["idea"]["generators"] == []


def test_generate_needs_claude_code_and_rejects_unknown_targets(client, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    denied = client.post("/api/tables/character/generate/ai", json={"draft": {}})
    assert denied.status_code == 403 and "CLAUDECODE" in denied.json()["detail"]

    monkeypatch.setenv("CLAUDECODE", "1")
    assert client.post("/api/tables/character/generate/nope", json={"draft": {}}).status_code == 404
    assert client.post("/api/tables/nope/generate/ai", json={"draft": {}}).status_code == 404
    assert client.post("/api/tables/character/generate/ai", json={"draft": {}, "args": {"nope": 1}}).status_code == 400


def test_generate_runs_the_entrance_as_a_job_with_the_draft(client, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    calls = []
    entrance = interface.entrance_of("story.generate_episode.GenerateEpisode")
    monkeypatch.setitem(interface.ENTRANCES, entrance.id, interface.Entrance(
        **{**entrance.__dict__, "target": lambda **kwargs: calls.append(kwargs) or {"id": 7, "text": "本文"}}))

    accepted = client.post("/api/tables/episode/generate/episode", json={
        "draft": {"story_id": 3, "title": "", "key": None, "start": "", "viewpoint": None, "text": ""},
        "args": {"character_ids": [1, 2], "model": ""}})
    assert accepted.status_code == 202, accepted.text
    job = _wait(client, accepted.json()["id"])
    assert job["status"] == "done" and job["result"]["id"] == 7 and job["entrance"] == entrance.id
    # 空の欄(None・空文字・空の配列)は「指定なし」なので渡さない
    assert calls[0]["episode"] == {"story_id": 3} and calls[0]["character_ids"] == [1, 2] and "model" not in calls[0]
