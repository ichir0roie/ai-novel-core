"""固定の一覧(`gui/api/interface.py`)と、画面が持つ書き出したもの(`gui/api/dump_static.py`)が、コードとずれていないか。"""
from gui.api import catalog, dump_static, interface


def test_entrance_lists_match_code():
    classes = catalog.entrance_classes()

    assert interface.DB_ENTRANCES == {id_ for id_, cls in classes.items() if not catalog.uses_claude(cls)}
    assert interface.CLAUDE_ENTRANCES == {id_ for id_, cls in classes.items() if catalog.uses_claude(cls)}
    for id_, cls in classes.items():
        assert interface.entrance_class(id_) is cls


def test_dumped_files_are_current():
    # ずれていたら `.venv/bin/python -m gui.api.dump_static` と `(cd gui/web && npm run types)` を回す
    for path, value in ((dump_static.OPENAPI_PATH, dump_static.openapi()), (dump_static.TABLES_PATH, dump_static.tables()),
                        (dump_static.ENTRANCES_PATH, dump_static.entrances())):
        with open(path, encoding="utf-8") as f:
            assert f.read() == dump_static.dumped(value), path


def test_tables():
    tables = {table["name"]: table for table in dump_static.tables()["tables"]}

    assert set(tables) == {"story", "episode", "character", "character_relation", "character_skill", "event", "location", "idea",
                           "meme", "oracle", "style_preference"}
    assert {child["name"] for child in tables["character"]["child_lists"]} == {"parameters", "locations", "histories"}


def test_entrances():
    entrances = {entrance["id"]: entrance for entrance in dump_static.entrances()["entrances"]}

    start_story = entrances["story.start_story.StartStory"]
    assert start_story["writes"] is False
    assert [param["name"] for param in start_story["params"]] == [
        "story_id", "time", "episodes", "count", "reach", "levels"]
    assert entrances["episode.delete_episode.DeleteEpisode"]["writes"] is True
    # claude を叩く入口は出さない
    assert "event.commit_event.CommitEvent" not in entrances
