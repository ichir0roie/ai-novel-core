"""GUI の「AI で作成」の API(`/api/tables/{table}/generate/{key}`)。claude を叩く入口を裏の job で回すこと。"""
import time

import pytest
from fastapi.testclient import TestClient

from ai.claude_code import ai_client
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
    # 登場人物は聞かない(下書きの character_ids、つまり話の episode_character を使う)
    assert {p["key"] for p in episode["episode"]["params"]} == {"previous_episode_ids", "model", "effort"}
    assert {p["key"] for p in episode["frame"]["params"]} == {"previous_episode_ids"}
    params = {p["key"]: p for p in episode["episode"]["params"]}
    # モデル・effort のプルダウンは ai_client の一覧をそのまま choices に出し、既定値は default に載せる
    assert params["model"]["choices"] == list(ai_client.AVAILABLE_MODELS)
    assert params["model"]["default"] == ai_client.EPISODE_MODEL
    assert params["effort"]["choices"] == list(ai_client.AVAILABLE_EFFORTS)
    assert params["effort"]["default"] == ai_client.EPISODE_EFFORT
    assert episode["revise"]["mode"] == "edit" and episode["revise"]["when_not_empty"] == "text"
    # 推敲は本文を見ながら大きく開く専用パネル(RevisePanel)の側で拾うので、小さなボタン列には出さない
    assert episode["revise"]["panel"] is True
    assert episode["episode"]["panel"] is False
    # 登場人物・直前の話は聞かない(登場人物は下書きの character_ids、直前の話は ReviseEpisode 側の既定)。
    # 専用レイアウトは指示文・モデル・effort だけ
    assert {p["key"] for p in episode["revise"]["params"]} == {"instruction", "model", "effort"}
    instruction = next(p for p in episode["revise"]["params"] if p["key"] == "instruction")
    assert instruction["required"] is True and instruction["nullable"] is False and instruction["section"] is True
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
        "draft": {"story_id": 3, "title": "", "key": None, "start": "", "viewpoint_character_id": None, "text": "",
                  "character_ids": [1, 2]},
        "args": {"model": ""}})
    assert accepted.status_code == 202, accepted.text
    job = _wait(client, accepted.json()["id"])
    assert job["status"] == "done" and job["result"]["id"] == 7 and job["entrance"] == entrance.id
    # 空の欄(None・空文字・空の配列)は「指定なし」なので渡さない
    assert calls[0]["episode"] == {"story_id": 3, "character_ids": [1, 2]} and "model" not in calls[0]
