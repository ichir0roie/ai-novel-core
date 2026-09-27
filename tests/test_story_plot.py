import json
import os

import pytest

from ai.claude_code import ai_client
from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story.commit_plot import CommitPlot
from ai.claude_code.interface.story.commit_story import CommitStory
from db.schema import Plot, EpisodeSummary, Episode, Location, Story
from db.stamp import Stamp
from tool.markdown.export_db import export_db
from tool.markdown.import_db import ImportDbError, import_db
from tool.markdown import sync_manifest
from tool.markdown.sync_db import sync_db


@pytest.fixture
def place(session):
    location = Location(name="ノウル", kind="星", text="")
    session.add(location)
    session.commit()
    return location.id


def test_commit_story_returns_row(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place,
                         "narration": "三人称", "state": "構想中",
                         "start": "11572/03/24 00:00:00", "text": "本編"}).run()
    assert story["name"] == "遥かなる幻想郷まで"
    assert story["place_id"] == place
    assert str(story["start"]) == "11572/03/24 00:00:00"


def test_commit_plot_summarizes_the_plot_right_away(session, place, monkeypatch):
    monkeypatch.setattr(ai_client, "try_generate_json",
                        lambda *a, **k: {"summary": "娘が生まれた", "style": "淡々とした語り"})
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    plot = CommitPlot({"story_id": story["id"],            "title": "白い灯り", "text": "骨組み"}).run()

    row = session.query(EpisodeSummary).filter_by(episode_id=session.get(Plot, plot["id"]).episode.id).one()
    assert (row.summary, row.style) == ("娘が生まれた", "淡々とした語り")


def test_commit_story_requires_name(place):
    with pytest.raises(ValueError):
        CommitStory({"place_id": place}).run()


def test_commit_story_rejects_unknown_place():
    with pytest.raises(UnknownRecordError):
        CommitStory({"name": "作品", "place_id": 9999}).run()


def test_plot_markdown_name_puts_story_id_and_start_first():
    start = Stamp(11572, 3, 25, 9, 30)
    assert Plot(id=7, story_id=1, start=start, title="白い灯り").markdown_name == \
        "1_11572-03-25-0930_白い灯り.md"
    assert Plot(id=8, story_id=1, start=start).markdown_name == "1_11572-03-25-0930.md"
    # 題だけを使う。filename は見ない
    assert Plot(id=9, story_id=2, start=start, title="題", filename="別名").markdown_name == \
        "2_11572-03-25-0930_題.md"
    # start が無ければ時刻の所を空ける
    assert Plot(id=10, story_id=2, title="題").markdown_name == "2__題.md"


def test_plot_parse_markdown_stem():
    start = Stamp(11572, 3, 25, 9, 30)
    assert Plot.parse_markdown_stem("1_11572-03-25-0930_白い灯り") == (
        None, {"story_id": 1, "start": start, "title": "白い灯り"})
    assert Plot.parse_markdown_stem("1_11572-03-25-0930") == (
        None, {"story_id": 1, "start": start, "title": None})
    assert Plot.parse_markdown_stem("2__題_二") == (None, {"story_id": 2, "start": None, "title": "題_二"})
    assert Plot.parse_markdown_stem("2_題") == (None, {"story_id": 2, "title": "題"})
    # 手で作った、数の付かない名前は story_id も決まらない
    assert Plot.parse_markdown_stem("下書き") == (None, {"filename": "下書き", "title": "下書き"})


STORY_DIR = os.path.join("story", "1_遥かなる幻想郷まで")
PLOT_MD = os.path.join(STORY_DIR, "1_11572-03-25-0000_白い灯り.md")
TEXT_TXT = os.path.join(STORY_DIR, "1_11572-03-25-0000_白い灯り.txt")


def _read(root, *parts):
    with open(os.path.join(root, *parts), encoding="utf-8") as f:
        return f.read()


def _write(root, relative, content):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_plot_round_trips_through_markdown(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "骨組み"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    assert os.listdir(os.path.join(root, "story")) == ["1_遥かなる幻想郷まで"]
    assert not os.path.exists(os.path.join(root, "plot"))

    import_db(root)
    session.expire_all()
    assert session.query(Plot).count() == 1
    plot = session.get(Plot, 1)
    assert (plot.story_id, str(plot.start), plot.title) == (1, "11572/03/25 00:00:00", "白い灯り")
    assert plot.filename is None and plot.directory_path is None
    assert plot.body == "骨組み"


def test_story_plot_and_text_are_nested(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place, "directory_path": "ノウル"}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "一話の本文"}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/04/01 00:00:00",
                "title": "裁定", "key": "種だけ"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    story_dir = os.path.join(root, "story", "ノウル", "1_遥かなる幻想郷まで")
    # 本文は話の md と同じ名前の .txt。本文の無い話(枠)は .txt を持たない
    # 作品の md は自分のディレクトリの先頭に並ぶ名前(`0_`)で置く
    assert sorted(os.listdir(story_dir)) == [
        "0_遥かなる幻想郷まで.md", "1_11572-03-25-0000_白い灯り.md", "1_11572-03-25-0000_白い灯り.txt", "1_11572-04-01-0000_裁定.md"]


def test_episode_is_the_body_only_txt(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00", "title": "白い灯り",
                "key": "## 出来事\n娘が生まれる", "text": "扉が開いた。\nミレアが来た。"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)

    assert _read(root, TEXT_TXT) == "扉が開いた。\nミレアが来た。\n"
    content = _read(root, PLOT_MD)
    assert "# data\n" in content and "# key\n## 出来事\n娘が生まれる" in content
    # 本文は話の md に出さない
    assert "# text" not in content and "扉が開いた" not in content and '"letters"' not in content


def test_edited_txt_updates_the_body(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, TEXT_TXT, "書き直した本文\n")
    result = sync_db(root)

    assert result["imported"] == {"episode": 1}
    session.expire_all()
    text = session.get(Episode, 1)
    assert (text.plot_id, text.text, text.letters) == (1, "書き直した本文", 7)


def test_hand_written_txt_beside_a_frame_becomes_its_body(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "key": "種"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, TEXT_TXT, "手で書いた本文\n")
    result = sync_db(root)

    assert result["imported"] == {"episode": 1}
    session.expire_all()
    plot = session.get(Plot, 1)
    assert plot.body == "手で書いた本文"
    assert (plot.episode.model, plot.episode.effort) == (None, None)
    assert _read(root, TEXT_TXT) == "手で書いた本文\n"


def test_removed_txt_removes_the_body(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    os.remove(os.path.join(root, TEXT_TXT))
    sync_db(root)

    session.expire_all()
    assert session.query(Episode).count() == 0
    assert session.get(Plot, 1).body == ""
    assert os.path.exists(os.path.join(root, PLOT_MD))


def test_plot_moved_under_another_story_follows_that_story(session, place, tmp_path):
    first = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    second = CommitStory({"name": "アルバ", "place_id": place}).run()
    CommitPlot({"story_id": first["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "key": "種"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    content = _read(root, PLOT_MD)
    os.remove(os.path.join(root, PLOT_MD))
    _write(root, os.path.join("story", "2_アルバ", "1_11572-03-25-0000_白い灯り.md"), content)
    sync_db(root)

    session.expire_all()
    assert session.get(Plot, 1).story_id == second["id"]
    assert sorted(os.listdir(os.path.join(root, "story", "2_アルバ"))) == [
        "0_アルバ.md", "2_11572-03-25-0000_白い灯り.md"]


def test_markdown_written_before_the_manifest_is_registered_without_importing(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)
    os.remove(os.path.join(str(tmp_path), ".markdown_sync.json"))

    result = sync_db(root)

    assert result["imported"] == {} and result["written"] == [] and result["conflicts"] == []


def test_plot_round_trips_without_start(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00", "title": "白い灯り",
                "text": "一話"}).run()
    second = CommitPlot({"story_id": story["id"], "title": "裁定", "text": "七話"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    assert sorted(name for name in os.listdir(os.path.join(root, STORY_DIR)) if name.endswith(".md")) == \
        ["0_遥かなる幻想郷まで.md", "1_11572-03-25-0000_白い灯り.md", "1__裁定.md"]

    import_db(root)
    session.expire_all()
    assert session.query(Plot).count() == 2
    plot = session.get(Plot, second["id"])
    assert (plot.story_id, plot.start, plot.title) == (1, None, "裁定")


def test_commit_plot_updates_by_id(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    first = CommitPlot({"story_id": story["id"], "title": "白い灯り", "key": "種"}).run()

    updated = CommitPlot({"id": first["id"], "text": "本文"}).run()

    assert updated["id"] == first["id"]
    assert (updated["key"], updated["text"], updated["letters"]) == ("種", "本文", 2)


def test_commit_plot_lays_out_the_text(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    plot = CommitPlot({"story_id": story["id"], "title": "白い灯り",
                             "text": "扉が開いた。ミレアが来た。\n◇\n三日後。"}).run()

    assert plot["text"] == "扉が開いた。\nミレアが来た。\n\n\n三日後。"
    assert plot["letters"] == len(plot["text"])


def test_commit_plot_rejects_unknown_id(place):
    with pytest.raises(UnknownRecordError):
        CommitPlot({"id": 9999, "text": "本文"}).run()


def test_commit_plot_requires_story_id_for_new_plot(place):
    with pytest.raises(ValueError):
        CommitPlot({"title": "白い灯り", "text": "本文"}).run()


def test_commit_plot_accepts_key_only(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    plot = CommitPlot({"story_id": story["id"], "title": "白い灯り",
                             "key": "人工母体から娘が生まれる", "start": "11572/03/25 00:00:00",
                             "viewpoint": "カシル", "place": "エンピレオ 血統管理省"}).run()
    assert plot["key"] == "人工母体から娘が生まれる"
    assert (plot["text"], plot["letters"]) == ("", 0)
    assert (plot["viewpoint"], plot["place"]) == ("カシル", "エンピレオ 血統管理省")
    assert str(plot["start"]) == "11572/03/25 00:00:00"


def test_commit_plot_requires_key_or_text(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    with pytest.raises(ValueError):
        CommitPlot({"story_id": story["id"], "title": "白い灯り"}).run()


def test_plot_markdown_has_data_and_key_sections(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "title": "白い灯り",
                "key": "## 出来事\n娘が生まれる", "text": "本文", "viewpoint": "カシル",
                "place": "エンピレオ", "start": "11572/03/25 00:00:00"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    content = _read(root, PLOT_MD)
    assert "# data\n" in content
    assert "## 出来事\n娘が生まれる" in content
    # 節として出す列は `# data` に出さない
    assert '"key"' not in content
    assert '"viewpoint": "カシル"' in content

    import_db(root)
    session.expire_all()
    plot = session.get(Plot, 1)
    assert (plot.key, plot.body) == ("## 出来事\n娘が生まれる", "本文")
    assert (plot.viewpoint, plot.place) == ("カシル", "エンピレオ")
    assert str(plot.start) == "11572/03/25 00:00:00"


def test_plot_markdown_keeps_empty_sections(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "title": "白い灯り",
                "key": "種だけ"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    import_db(root)
    session.expire_all()
    plot = session.get(Plot, 1)
    assert (plot.key, plot.body) == ("種だけ", "")


def test_story_markdown_name_uses_name(session, place, tmp_path):
    CommitStory({"name": "遥かなる幻想郷まで", "place_id": place,
                 "filename": "遥かなる幻想郷まで"}).run()
    root = str(tmp_path / "worlds")
    export_db(root)
    assert os.listdir(os.path.join(root, STORY_DIR)) == ["0_遥かなる幻想郷まで.md"]

    # 手で直していない md は取り込まないので、本文に手を入れて取り込ませる
    path = os.path.join(root, STORY_DIR, "0_遥かなる幻想郷まで.md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(content + "追記\n")
    import_db(root)
    session.expire_all()
    assert session.get(Story, 1).filename is None
    assert session.get(Story, 1).markdown_name == "1_遥かなる幻想郷まで.md"


def test_story_markdown_name_follows_name_edited_in_markdown(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで・アルバ編", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    export_db(root)
    path = os.path.join(root, "story", "1_遥かなる幻想郷まで・アルバ編", "0_遥かなる幻想郷まで・アルバ編.md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.replace('"name": "遥かなる幻想郷まで・アルバ編"', '"name": "アルバ"'))

    import_db(root)
    export_db(root)
    # 話と本文もディレクトリごと付いていく
    assert os.listdir(os.path.join(root, "story")) == ["1_アルバ"]
    assert sorted(os.listdir(os.path.join(root, "story", "1_アルバ"))) == [
        "0_アルバ.md", "1_11572-03-25-0000_白い灯り.md", "1_11572-03-25-0000_白い灯り.txt"]


def test_plot_moves_with_its_txt_under_another_story(session, place, tmp_path):
    first = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    second = CommitStory({"name": "アルバ", "place_id": place}).run()
    CommitPlot({"story_id": first["id"], "start": "11572/03/25 00:00:00",
                "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    moved = os.path.join(root, "story", "2_アルバ")
    for name in ("1_11572-03-25-0000_白い灯り.md", "1_11572-03-25-0000_白い灯り.txt"):
        os.rename(os.path.join(root, STORY_DIR, name), os.path.join(moved, name))
    sync_db(root)

    session.expire_all()
    assert session.get(Plot, 1).story_id == second["id"]
    assert session.get(Plot, 1).body == "一話" and session.query(Episode).count() == 1
    assert sorted(os.listdir(moved)) == [
        "0_アルバ.md", "2_11572-03-25-0000_白い灯り.md", "2_11572-03-25-0000_白い灯り.txt"]


def test_txt_without_a_plot_md_is_registered_with_an_empty_plot(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, os.path.join(STORY_DIR, "メモ.txt"), "覚え書き\n")
    result = sync_db(root)

    assert result["imported"] == {"plot": 1, "episode": 1}
    session.expire_all()
    plot = session.query(Plot).one()
    assert (plot.story_id, plot.title, plot.key, plot.start) == (story["id"], "メモ", "", None)
    assert plot.body == "覚え書き"
    assert sorted(os.listdir(os.path.join(root, STORY_DIR))) == ["0_遥かなる幻想郷まで.md", "1__メモ.md", "1__メモ.txt"]


def test_txt_in_a_directory_without_a_story_md_is_registered_with_an_empty_story(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, os.path.join("story", "未定", "新作", "1_11600-01-01-0000_はじまり.txt"), "一話\n")
    result = sync_db(root)

    assert result["imported"] == {"story": 1, "plot": 1, "episode": 1}
    session.expire_all()
    story = session.query(Story).one()
    plot = session.query(Plot).one()
    assert (story.name, story.directory_path, story.narration, story.state, story.text) == ("新作", "未定", "", "", "")
    assert (plot.story_id, plot.title, str(plot.start)) == (story.id, "はじまり", "11600/01/01 00:00:00")
    assert plot.body == "一話"
    assert sorted(os.listdir(os.path.join(root, "story", "未定", f"{story.id}_新作"))) == [
        "0_新作.md", f"{story.id}_11600-01-01-0000_はじまり.md", f"{story.id}_11600-01-01-0000_はじまり.txt"]


def test_story_md_without_data_is_registered_with_empty_columns(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, os.path.join("story", "新作", "0_新作.md"), "筋書き\n")
    sync_db(root)

    session.expire_all()
    story = session.query(Story).one()
    assert (story.name, story.text, story.narration, story.state) == ("新作", "筋書き", "", "")


def test_txt_right_under_the_story_directory_stops_the_sync(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, os.path.join("story", "メモ.txt"), "覚え書き\n")

    with pytest.raises(ImportDbError):
        sync_db(root)
    assert os.listdir(os.path.join(root, "story")) == ["メモ.txt"]


def test_txt_outside_the_story_tree_is_left_alone(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    _write(root, os.path.join("idea", "メモ.txt"), "覚え書き\n")

    sync_db(root)

    assert _read(root, "idea", "メモ.txt") == "覚え書き\n"


def test_story_record_is_named_to_come_first_in_its_directory():
    story = Story(id=12, name="仮史：生成時代")
    assert (story.markdown_name, story.record_name) == ("12_仮史：生成時代.md", "0_仮史：生成時代.md")
    # 話の md は作品の id(1 から)で始まるので、ASCII 順でも作品の md が先に来る
    assert sorted([Plot(story_id=12, start=Stamp(2034, 5, 20), title="無断学習").markdown_name,
                   story.record_name]) == ["0_仮史：生成時代.md", "12_2034-05-20-0000_無断学習.md"]


def test_hand_made_story_directory_is_imported_with_its_plots(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    sync_db(root)
    _write(root, os.path.join("story", "未定", "新作", "0_新作.md"), "新作の筋書き\n")
    _write(root, os.path.join("story", "未定", "新作", "下書きの話.md"), "話の種\n")
    _write(root, os.path.join("story", "未定", "新作", "下書きの話.txt"), "話の本文\n")

    result = sync_db(root)

    assert result["imported"] == {"story": 1, "plot": 1, "episode": 1}
    session.expire_all()
    story = session.query(Story).one()
    plot = session.query(Plot).one()
    assert (story.name, story.text, story.directory_path) == ("新作", "新作の筋書き", "未定")
    assert (plot.story_id, plot.key, plot.body) == (story.id, "話の種", "話の本文")
    assert sorted(os.listdir(os.path.join(root, "story", "未定"))) == [f"{story.id}_新作"]


def test_manifest_from_before_the_rename_is_read_with_the_new_table_names(session, place, tmp_path):
    # db だけが pull で改名済みになって届き、台帳が改名前の表の名前のまま残っている場合
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitPlot({"story_id": story["id"], "start": "11572/03/25 00:00:00", "title": "白い灯り",
                "key": "種", "text": "本文"}).run()
    root = str(tmp_path / "worlds")
    export_db(root)
    path = sync_manifest.manifest_path(root)
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    legacy = {"plot": "episode", "episode": "episode_text"}
    for entry in entries.values():
        entry["table"] = legacy.get(entry["table"], entry["table"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)

    manifest = sync_manifest.Manifest(root)
    assert manifest.get(os.path.join(root, PLOT_MD))["table"] == "plot"
    assert manifest.get(os.path.join(root, TEXT_TXT))["table"] == "episode"
    result = sync_db(root)
    assert (result["imported"], result["deleted"], result["written"], result["removed"]) == ({}, [], [], [])
    session.expire_all()
    assert session.get(Plot, 1).body == "本文"
