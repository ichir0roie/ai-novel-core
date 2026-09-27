"""データ編集 GUI の API(`gui/api`)。読みは select、書きは入口の `execute` 越しに db へ届くこと。"""
import pytest
from fastapi.testclient import TestClient

from db.schema import (
    Character, CharacterParameter, ConfirmStatus, Event, EventCharacter, Idea, Location, Meme, Plot, Story,
)
from db.stamp import Stamp
from gui.api import app as app_module


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture
def world(session):
    world = Location(name="世界線", kind="世界線", text="")
    session.add(world)
    session.flush()
    village = Location(name="村", kind="村", text="", parent_id=world.id)
    session.add(village)
    session.flush()
    story = Story(name="村の話", place_id=village.id, text="", narration="", state="執筆中")
    session.add(story)
    session.commit()
    return {"world": world.id, "village": village.id, "story": story.id}


def test_tables_meta_comes_from_schema(client, session):
    session.add(Idea(name="魔力", kind="技術", text=""))
    session.commit()

    tables = {table["name"]: table for table in client.get("/api/tables").json()["tables"]}

    assert list(tables) == ["story", "plot", "character", "character_relation", "event", "location",
                            "idea", "meme", "oracle"]
    assert tables["idea"]["count"] == 1 and tables["idea"]["reviewable"] is True
    columns = {column["key"]: column for column in tables["idea"]["columns"]}
    assert columns["confirmed"]["type"] == "confirm" and columns["confirmed"]["choices"] == ["未確認", "承認", "非承認"]
    assert columns["location_id"]["references"] == "location"
    assert columns["start"]["type"] == "stamp"
    assert columns["text"]["section"] is True and columns["text"]["label"] == "本文"
    assert columns["id"]["readonly"] is True
    # 話は本文(episode)を text として持ち、字数は読むだけ
    plot_columns = {column["key"]: column for column in tables["plot"]["columns"]}
    assert plot_columns["text"]["section"] is True and plot_columns["letters"]["readonly"] is True
    assert [child["name"] for child in tables["character"]["child_lists"]] == ["parameters"]
    assert {column["key"] for column in tables["character"]["child_lists"][0]["columns"]} >= {"family_name", "tone"}
    assert {column["key"]: column["create_only"] for column in tables["character"]["columns"]}["place_id"] is True
    meme_columns = {column["key"]: column for column in tables["meme"]["columns"]}
    assert meme_columns["category"]["choices"] == ["信条", "欲求", "境遇", "集団", "理"]


def test_list_searches_filters_and_labels_references(client, session, world):
    session.add_all([
        Idea(name="魔力", kind="技術", text="世界の力", location_id=world["world"]),
        Idea(name="宿り", kind="技術", text="体に虫を宿す治療", confirmed=ConfirmStatus.PENDING),
        Idea(name="虫憑き", kind="呼称", text="", confirmed=ConfirmStatus.REJECTED),
    ])
    session.commit()

    body = client.get("/api/tables/idea/records").json()
    assert body["total"] == 3 and [item["name"] for item in body["items"]] == ["魔力", "宿り", "虫憑き"]
    assert "text" not in body["items"][0] and body["items"][0]["preview"] == "世界の力"
    assert body["labels"]["location_id"] == {str(world["world"]): "世界線"}

    assert [item["name"] for item in client.get("/api/tables/idea/records?q=虫").json()["items"]] == ["宿り", "虫憑き"]
    assert [item["name"] for item in client.get("/api/tables/idea/records?confirmed=非承認").json()["items"]] == ["虫憑き"]
    assert [item["name"] for item in client.get("/api/tables/idea/records?kind=技術&order=desc").json()["items"]] == ["宿り", "魔力"]
    assert [item["name"] for item in client.get("/api/tables/idea/records?location_id=null").json()["items"]] == ["宿り", "虫憑き"]
    page = client.get("/api/tables/idea/records?limit=1&offset=1").json()
    assert page["total"] == 3 and [item["name"] for item in page["items"]] == ["宿り"]

    options = client.get("/api/tables/location/options?q=村").json()["items"]
    assert options == [{"id": world["village"], "label": "村"}]
    assert client.get("/api/tables/nope/records").status_code == 404


def test_create_update_and_errors_go_through_the_entrances(client, session, world):
    created = client.post("/api/tables/idea/records", json={
        "name": "宿り", "kind": "技術", "text": "体に虫を宿す治療", "location_id": world["world"], "start": "2100"})
    assert created.status_code == 201, created.text
    record = created.json()["record"]
    assert record["confirmed"] == "承認" and record["start"] == "2100/01/01 00:00:00"
    assert created.json()["labels"]["location_id"] == {str(world["world"]): "世界線"}

    updated = client.patch(f"/api/tables/idea/records/{record['id']}", json={"kind": "呼称", "confirmed": "未確認"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["record"]["kind"] == "呼称" and updated.json()["record"]["confirmed"] == "未確認"
    assert updated.json()["record"]["text"] == "体に虫を宿す治療"
    assert session.get(Idea, record["id"]).kind == "呼称"

    assert client.post("/api/tables/idea/records", json={"kind": "技術"}).status_code == 400
    assert client.patch(f"/api/tables/idea/records/{record['id']}", json={"nope": 1}).status_code == 400
    assert client.patch(f"/api/tables/idea/records/{record['id']}", json={"location_id": 999}).status_code == 404
    assert client.patch("/api/tables/idea/records/999", json={"kind": "技術"}).status_code == 404
    assert client.patch(f"/api/tables/idea/records/{record['id']}", json={"confirmed": "maybe"}).status_code == 400
    assert client.get("/api/tables/idea/records/999").status_code == 404


def test_character_with_parameters_and_birthplace(client, session, world):
    created = client.post("/api/tables/character/records", json={
        "name": "ノア", "text": "# plot\n少年", "start": "2100/04/01", "place_id": world["village"],
        "parameters": [{"family_name": "リヴ", "tone": "ぶっきらぼう"}]})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["record"]["parameters"][0]["family_name"] == "リヴ"
    assert body["related"]["places"] == [
        {"location_id": world["village"], "location": "村", "start": "2100/04/01 00:00:00", "end": None}]

    updated = client.patch(f"/api/tables/character/records/{body['record']['id']}", json={
        "parameters": [{"family_name": "リヴ", "tone": "静か"}, {"start": "2120", "family_name": "アルト"}],
        "place_id": 999})
    assert updated.status_code == 200, updated.text
    assert [p["family_name"] for p in updated.json()["record"]["parameters"]] == ["リヴ", "アルト"]
    assert session.query(CharacterParameter).count() == 2


def test_plot_text_goes_to_episode_and_synced_is_kept(client, session, world):
    created = client.post("/api/tables/plot/records", json={
        "story_id": world["story"], "title": "旅立ち", "key": "村を出る", "text": "本文です。", "start": "2100/04/01"})
    assert created.status_code == 201, created.text
    record = created.json()["record"]
    assert record["text"] == "本文です。" and record["letters"] == 5 and record["synced"] is False
    assert created.json()["labels"]["story_id"] == {str(world["story"]): "村の話"}

    updated = client.patch(f"/api/tables/plot/records/{record['id']}", json={"text": "直した本文。", "synced": True})
    assert updated.json()["record"]["text"] == "直した本文。" and updated.json()["record"]["synced"] is True
    session.expire_all()
    assert session.get(Plot, record["id"]).body == "直した本文。"

    listed = client.get(f"/api/tables/plot/records?story_id={world['story']}").json()
    assert listed["items"][0]["label"] == "旅立ち" and "text" not in listed["items"][0]
    story = client.get(f"/api/tables/story/records/{world['story']}").json()
    assert story["related"]["plots"][0]["label"] == "旅立ち"


def test_event_participants(client, session, world):
    a = Character(name="甲", text="")
    b = Character(name="乙", text="")
    session.add_all([a, b])
    session.commit()

    created = client.post("/api/tables/event/records", json={
        "name": "峠越え", "text": "", "time": "2100/04/01", "location_id": world["village"], "character_ids": [a.id]})
    assert created.status_code == 201, created.text
    assert created.json()["record"]["character_ids"] == [a.id]
    assert created.json()["labels"]["character_ids"] == {str(a.id): "甲"}

    event_id = created.json()["record"]["id"]
    updated = client.patch(f"/api/tables/event/records/{event_id}", json={"character_ids": [b.id], "name": "峠越え(改)"})
    assert updated.json()["record"]["character_ids"] == [b.id] and updated.json()["record"]["name"] == "峠越え(改)"
    assert [row.character_id for row in session.query(EventCharacter)] == [b.id]
    assert client.patch(f"/api/tables/event/records/{event_id}", json={"character_ids": [999]}).status_code == 404


def test_meme_create_defaults_to_approved(client, session):
    created = client.post("/api/tables/meme/records", json={"text": "約束を守る", "category": "信条"})
    assert created.status_code == 201, created.text
    assert created.json()["record"]["confirmed"] == "承認" and created.json()["record"]["directory_path"] == "信条"
    assert client.post("/api/tables/meme/records", json={"text": "x", "category": "変"}).status_code == 400
    assert client.post("/api/tables/meme/records", json={"text": " "}).status_code == 400


def test_review_flow_approves_and_rejects_in_order(client, session):
    session.add_all([
        Idea(name="宿り", kind="技術", text="a", confirmed=ConfirmStatus.PENDING),
        Idea(name="虫憑き", kind="呼称", text="b", confirmed=ConfirmStatus.PENDING),
        Idea(name="魔力", kind="技術", text="c"),
        Meme(text="約束を守る", category="信条"),
    ])
    session.commit()
    ids = {idea.name: idea.id for idea in session.query(Idea)}

    summary = {row["table"]: row for row in client.get("/api/review").json()["tables"]}
    assert (summary["idea"]["pending"], summary["idea"]["approved"], summary["idea"]["rejected"]) == (2, 1, 0)
    assert summary["meme"]["pending"] == 1

    first = client.get("/api/review/idea/next").json()
    assert first["record"]["name"] == "宿り" and first["remaining"] == 2 and first["related"] == {"appearances": []}

    decided = client.post(f"/api/review/idea/{ids['宿り']}", json={"decision": "承認", "changes": {"kind": "医療"}})
    assert decided.status_code == 200, decided.text
    assert decided.json()["record"]["confirmed"] == "承認" and decided.json()["record"]["kind"] == "医療"

    second = client.get("/api/review/idea/next").json()
    assert second["record"]["name"] == "虫憑き" and second["remaining"] == 1
    # 飛ばして末尾を過ぎたら先頭へ戻る
    assert client.get(f"/api/review/idea/next?after={ids['虫憑き']}").json()["record"]["name"] == "虫憑き"

    client.post(f"/api/review/idea/{ids['虫憑き']}", json={"decision": "非承認"})
    done = client.get("/api/review/idea/next").json()
    assert done["record"] is None and done["remaining"] == 0
    assert session.get(Idea, ids["虫憑き"]).confirmed == ConfirmStatus.REJECTED

    meme_id = session.query(Meme).one().id
    assert client.post(f"/api/review/meme/{meme_id}", json={"decision": "承認"}).json()["record"]["confirmed"] == "承認"
    assert client.get("/api/review/meme/next").json()["record"] is None
    assert client.post(f"/api/review/meme/{meme_id}", json={"decision": "変"}).status_code == 422
    assert client.get("/api/review/story/next").status_code == 404


def test_sync_endpoint_runs_sync_db(client, monkeypatch):
    calls = []

    class _Stub:
        def run(self):
            calls.append(True)
            return {"imported": {}, "deleted": [], "conflicts": [], "written": [], "removed": []}

    monkeypatch.setattr(app_module, "SyncDb", _Stub)
    assert client.post("/api/sync").json()["conflicts"] == [] and calls == [True]
