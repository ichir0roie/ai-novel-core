"""`ai/claude_code/interface/` の入口を GUI の API から呼ぶ(`/api/interface`)。
claude コマンドを叩く入口は Claude Code の環境(CLAUDECODE=1)でだけ、裏の job として走ること。"""
import time

import pytest
from fastapi.testclient import TestClient

from db.schema import Location
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


def test_catalog_lists_entrances_with_params_and_claude_flags(client, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    body = client.get("/api/interface").json()
    entrances = {entrance["id"]: entrance for entrance in body["entrances"]}

    assert body["claude_available"] is False
    places = entrances["world.list_places.ListPlaces"]
    assert places["area"] == "world" and places["claude"] is False and places["writes"] is False
    assert places["params"] == [{"name": "kind", "required": False, "default": None, "annotation": "str | None"}]

    assert entrances["randomizer.update_idea.UpdateIdea"]["claude"] is False
    assert entrances["randomizer.update_idea.UpdateIdea"]["writes"] is True
    # 確定のあとに AI を回す入口・AI を受け取る入口・常駐ループ側は claude を叩く
    for entrance_id in ("randomizer.commit_idea.CommitIdea", "randomizer.commit_oracle.CommitOracle",
                        "randomizer.commit_event.CommitEvent", "randomizer.update_event.UpdateEvent",
                        "story.commit_plot.CommitPlot", "story.commit_story.CommitStory",
                        "fact_check.check_facts.CheckFacts", "meme.extract_memes.ExtractMemes",
                        "meme.refresh_generated_content.RefreshGeneratedContent",
                        "randomizer.generate_characters.GenerateCharacters",
                        "time_keeper.daily_event", "time_keeper.plot", "time_keeper.write_story"):
        assert entrances[entrance_id]["claude"] is True, entrance_id
    assert [p["name"] for p in entrances["time_keeper.place_event"]["params"]] == [
        "place_id", "time", "key", "shared_style_extra", "style_extra"]
    assert entrances["randomizer.generate_characters.GenerateCharacters"]["params"][2]["default"] == [2, 4]


def test_plain_entrance_runs_synchronously(client, session):
    session.add_all([Location(name="村", kind="村", text=""), Location(name="町", kind="町", text="")])
    session.commit()

    result = client.post("/api/interface/world.list_places.ListPlaces", json={"args": {"kind": "村"}})
    assert result.status_code == 200, result.text
    assert [row["name"] for row in result.json()["result"]] == ["村"]

    created = client.post("/api/interface/randomizer.commit_meme.CommitMeme",
                          json={"args": {"meme": {"text": "約束を守る", "category": "信条"}}})
    assert created.status_code == 200 and created.json()["result"]["confirmed"] == "承認"

    assert client.post("/api/interface/world.list_places.ListPlaces", json={"args": {"nope": 1}}).status_code == 400
    assert client.post("/api/interface/world.nope.Nope", json={}).status_code == 404
    assert client.post("/api/interface/randomizer.commit_meme.CommitMeme",
                       json={"args": {"meme": {"text": ""}}}).status_code == 400


def test_background_job_returns_id_and_result(client, session):
    session.add(Location(name="村", kind="村", text=""))
    session.commit()

    accepted = client.post("/api/interface/world.list_places.ListPlaces", json={"args": {}, "background": True})
    assert accepted.status_code == 202, accepted.text
    job = _wait(client, accepted.json()["id"])
    assert job["status"] == "done" and [row["name"] for row in job["result"]] == ["村"]
    assert accepted.json()["id"] in {job["id"] for job in client.get("/api/jobs").json()["jobs"]}
    assert client.get("/api/jobs/nope").status_code == 404


def test_claude_entrances_need_claude_code_environment(client, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    denied = client.post("/api/interface/time_keeper.daily_event", json={"args": {}})
    assert denied.status_code == 403 and "CLAUDECODE" in denied.json()["detail"]
    assert client.post("/api/interface/randomizer.commit_idea.CommitIdea",
                       json={"args": {"idea": {"name": "x", "kind": "技術"}}}).status_code == 403

    monkeypatch.setenv("CLAUDECODE", "1")
    calls = []
    entrance = interface.entrance_of("time_keeper.daily_event")
    monkeypatch.setitem(interface.ENTRANCES, entrance.id, interface.Entrance(
        **{**entrance.__dict__, "target": lambda **kwargs: calls.append(kwargs) or 42}))
    accepted = client.post("/api/interface/time_keeper.daily_event", json={"args": {"character_id": 3}})
    assert accepted.status_code == 202, accepted.text
    job = _wait(client, accepted.json()["id"])
    assert job["status"] == "done" and job["result"] == 42 and job["entrance"] == "time_keeper.daily_event"
    assert calls[0]["character_id"] == 3
    assert client.get("/api/interface").json()["claude_available"] is True


def test_failed_job_keeps_the_error(client, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    entrance = interface.entrance_of("time_keeper.loop")

    def boom(**_kwargs):
        raise RuntimeError("claude が落ちた")

    monkeypatch.setitem(interface.ENTRANCES, entrance.id, interface.Entrance(**{**entrance.__dict__, "target": boom}))
    accepted = client.post("/api/interface/time_keeper.loop", json={"args": {"max_days": 1}})
    job = _wait(client, accepted.json()["id"])
    assert job["status"] == "failed" and "claude が落ちた" in job["error"]


def test_style_defaults_come_from_the_world_instructions(monkeypatch):
    import sys
    import types

    style = types.ModuleType("instructions.style")
    style.SHARED_EXTRA, style.EPISODE_STYLE_EXTRA = "共有の癖", "本文の癖"
    monkeypatch.setitem(sys.modules, "instructions", types.ModuleType("instructions"))
    monkeypatch.setitem(sys.modules, "instructions.style", style)

    entrance = interface.entrance_of("time_keeper.episode")
    filled = interface._style_defaults({"plot_id": 1, "style_extra": "自分で渡した"}, entrance.params)
    assert filled == {"plot_id": 1, "style_extra": "自分で渡した", "shared_style_extra": "共有の癖"}
    assert interface._style_defaults({"kind": None}, interface.entrance_of("world.list_places.ListPlaces").params) == {"kind": None}
