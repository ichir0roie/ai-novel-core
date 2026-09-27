import os

import pytest

from ai.claude_code import ai_client
from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story.commit_episode import CommitEpisode
from ai.claude_code.interface.story.commit_story import CommitStory
from db.schema import Episode, EpisodeSummary, EpisodeText, Location, Story
from db.stamp import Stamp
from tool.markdown.export_db import export_db
from tool.markdown.import_db import ImportDbError, import_db
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


def test_commit_episode_summarizes_the_episode_right_away(session, place, monkeypatch):
    monkeypatch.setattr(ai_client, "try_generate_json",
                        lambda *a, **k: {"summary": "娘が生まれた", "style": "淡々とした語り"})
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    episode = CommitEpisode({"story_id": story["id"],            "title": "白い灯り", "text": "骨組み"}).run()

    row = session.query(EpisodeSummary).filter_by(episode_id=episode["id"]).one()
    assert (row.summary, row.style) == ("娘が生まれた", "淡々とした語り")


def test_commit_story_requires_name(place):
    with pytest.raises(ValueError):
        CommitStory({"place_id": place}).run()


def test_commit_story_rejects_unknown_place():
    with pytest.raises(UnknownRecordError):
        CommitStory({"name": "作品", "place_id": 9999}).run()


def test_episode_markdown_name_puts_story_id_and_start_first():
    start = Stamp(11572, 3, 25, 9, 30)
    assert Episode(id=7, story_id=1, start=start, title="白い灯り").markdown_name == \
        "1_11572-03-25-0930_白い灯り.md"
    assert Episode(id=8, story_id=1, start=start).markdown_name == "1_11572-03-25-0930.md"
    # 題だけを使う。filename は見ない
    assert Episode(id=9, story_id=2, start=start, title="題", filename="別名").markdown_name == \
        "2_11572-03-25-0930_題.md"
    # start が無ければ時刻の所を空ける
    assert Episode(id=10, story_id=2, title="題").markdown_name == "2__題.md"


def test_episode_parse_markdown_stem():
    start = Stamp(11572, 3, 25, 9, 30)
    assert Episode.parse_markdown_stem("1_11572-03-25-0930_白い灯り") == (
        None, {"story_id": 1, "start": start, "title": "白い灯り"})
    assert Episode.parse_markdown_stem("1_11572-03-25-0930") == (
        None, {"story_id": 1, "start": start, "title": None})
    assert Episode.parse_markdown_stem("2__題_二") == (None, {"story_id": 2, "start": None, "title": "題_二"})
    assert Episode.parse_markdown_stem("2_題") == (None, {"story_id": 2, "title": "題"})
    # 手で作った、数の付かない名前は story_id も決まらない
    assert Episode.parse_markdown_stem("下書き") == (None, {"filename": "下書き", "title": "下書き"})


STORY_DIR = os.path.join("story", "1_遥かなる幻想郷まで")
EPISODE_MD = os.path.join(STORY_DIR, "1_11572-03-25-0000_白い灯り.md")
TEXT_TXT = os.path.join(STORY_DIR, "1_11572-03-25-0000_白い灯り.txt")


def _read(root, *parts):
    with open(os.path.join(root, *parts), encoding="utf-8") as f:
        return f.read()


def _write(root, relative, content):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_episode_round_trips_through_markdown(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "text": "骨組み"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    assert os.listdir(os.path.join(root, "story")) == ["1_遥かなる幻想郷まで"]
    assert not os.path.exists(os.path.join(root, "episode"))

    import_db(root)
    session.expire_all()
    assert session.query(Episode).count() == 1
    episode = session.get(Episode, 1)
    assert (episode.story_id, str(episode.start), episode.title) == (1, "11572/03/25 00:00:00", "白い灯り")
    assert episode.filename is None and episode.directory_path is None
    assert episode.body == "骨組み"


def test_story_episode_and_text_are_nested(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place, "directory_path": "ノウル"}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "text": "一話の本文"}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/04/01 00:00:00",
                   "title": "裁定", "key": "種だけ"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    story_dir = os.path.join(root, "story", "ノウル", "1_遥かなる幻想郷まで")
    # 本文は話の md と同じ名前の .txt。本文の無い話(枠)は .txt を持たない
    # 作品の md は自分のディレクトリの先頭に並ぶ名前(`0_`)で置く
    assert sorted(os.listdir(story_dir)) == [
        "0_遥かなる幻想郷まで.md", "1_11572-03-25-0000_白い灯り.md", "1_11572-03-25-0000_白い灯り.txt", "1_11572-04-01-0000_裁定.md"]


def test_episode_text_is_the_body_only_txt(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00", "title": "白い灯り",
                   "key": "## 出来事\n娘が生まれる", "text": "扉が開いた。\nミレアが来た。"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)

    assert _read(root, TEXT_TXT) == "扉が開いた。\nミレアが来た。\n"
    content = _read(root, EPISODE_MD)
    assert "# data\n" in content and "# key\n## 出来事\n娘が生まれる" in content
    # 本文は話の md に出さない
    assert "# text" not in content and "扉が開いた" not in content and '"letters"' not in content


def test_edited_txt_updates_the_body(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, TEXT_TXT, "書き直した本文\n")
    result = sync_db(root)

    assert result["imported"] == {"episode_text": 1}
    session.expire_all()
    text = session.get(EpisodeText, 1)
    assert (text.episode_id, text.text, text.letters) == (1, "書き直した本文", 7)


def test_hand_written_txt_beside_a_frame_becomes_its_body(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "key": "種"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, TEXT_TXT, "手で書いた本文\n")
    result = sync_db(root)

    assert result["imported"] == {"episode_text": 1}
    session.expire_all()
    episode = session.get(Episode, 1)
    assert episode.body == "手で書いた本文"
    assert (episode.episode_text.model, episode.episode_text.effort) == (None, None)
    assert _read(root, TEXT_TXT) == "手で書いた本文\n"


def test_removed_txt_removes_the_body(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    os.remove(os.path.join(root, TEXT_TXT))
    sync_db(root)

    session.expire_all()
    assert session.query(EpisodeText).count() == 0
    assert session.get(Episode, 1).body == ""
    assert os.path.exists(os.path.join(root, EPISODE_MD))


def test_episode_moved_under_another_story_follows_that_story(session, place, tmp_path):
    first = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    second = CommitStory({"name": "アルバ", "place_id": place}).run()
    CommitEpisode({"story_id": first["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "key": "種"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    content = _read(root, EPISODE_MD)
    os.remove(os.path.join(root, EPISODE_MD))
    _write(root, os.path.join("story", "2_アルバ", "1_11572-03-25-0000_白い灯り.md"), content)
    sync_db(root)

    session.expire_all()
    assert session.get(Episode, 1).story_id == second["id"]
    assert sorted(os.listdir(os.path.join(root, "story", "2_アルバ"))) == [
        "0_アルバ.md", "2_11572-03-25-0000_白い灯り.md"]


def test_markdown_written_before_the_manifest_is_registered_without_importing(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)
    os.remove(os.path.join(str(tmp_path), ".markdown_sync.json"))

    result = sync_db(root)

    assert result["imported"] == {} and result["written"] == [] and result["conflicts"] == []


def test_episode_round_trips_without_start(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00", "title": "白い灯り",
                   "text": "一話"}).run()
    second = CommitEpisode({"story_id": story["id"], "title": "裁定", "text": "七話"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    assert sorted(name for name in os.listdir(os.path.join(root, STORY_DIR)) if name.endswith(".md")) == \
        ["0_遥かなる幻想郷まで.md", "1_11572-03-25-0000_白い灯り.md", "1__裁定.md"]

    import_db(root)
    session.expire_all()
    assert session.query(Episode).count() == 2
    episode = session.get(Episode, second["id"])
    assert (episode.story_id, episode.start, episode.title) == (1, None, "裁定")


def test_commit_episode_updates_by_id(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    first = CommitEpisode({"story_id": story["id"], "title": "白い灯り", "key": "種"}).run()

    updated = CommitEpisode({"id": first["id"], "text": "本文"}).run()

    assert updated["id"] == first["id"]
    assert (updated["key"], updated["text"], updated["letters"]) == ("種", "本文", 2)


def test_commit_episode_lays_out_the_text(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()

    episode = CommitEpisode({"story_id": story["id"], "title": "白い灯り",
                             "text": "扉が開いた。ミレアが来た。\n◇\n三日後。"}).run()

    assert episode["text"] == "扉が開いた。\nミレアが来た。\n\n\n三日後。"
    assert episode["letters"] == len(episode["text"])


def test_commit_episode_rejects_unknown_id(place):
    with pytest.raises(UnknownRecordError):
        CommitEpisode({"id": 9999, "text": "本文"}).run()


def test_commit_episode_requires_story_id_for_new_episode(place):
    with pytest.raises(ValueError):
        CommitEpisode({"title": "白い灯り", "text": "本文"}).run()


def test_commit_episode_accepts_key_only(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    episode = CommitEpisode({"story_id": story["id"], "title": "白い灯り",
                             "key": "人工母体から娘が生まれる", "start": "11572/03/25 00:00:00",
                             "viewpoint": "カシル", "place": "エンピレオ 血統管理省"}).run()
    assert episode["key"] == "人工母体から娘が生まれる"
    assert (episode["text"], episode["letters"]) == ("", 0)
    assert (episode["viewpoint"], episode["place"]) == ("カシル", "エンピレオ 血統管理省")
    assert str(episode["start"]) == "11572/03/25 00:00:00"


def test_commit_episode_requires_key_or_text(place):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    with pytest.raises(ValueError):
        CommitEpisode({"story_id": story["id"], "title": "白い灯り"}).run()


def test_episode_markdown_has_data_and_key_sections(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "title": "白い灯り",
                   "key": "## 出来事\n娘が生まれる", "text": "本文", "viewpoint": "カシル",
                   "place": "エンピレオ", "start": "11572/03/25 00:00:00"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    content = _read(root, EPISODE_MD)
    assert "# data\n" in content
    assert "## 出来事\n娘が生まれる" in content
    # 節として出す列は `# data` に出さない
    assert '"key"' not in content
    assert '"viewpoint": "カシル"' in content

    import_db(root)
    session.expire_all()
    episode = session.get(Episode, 1)
    assert (episode.key, episode.body) == ("## 出来事\n娘が生まれる", "本文")
    assert (episode.viewpoint, episode.place) == ("カシル", "エンピレオ")
    assert str(episode.start) == "11572/03/25 00:00:00"


def test_episode_markdown_keeps_empty_sections(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    CommitEpisode({"story_id": story["id"], "title": "白い灯り",
                   "key": "種だけ"}).run()

    root = str(tmp_path / "worlds")
    export_db(root)
    import_db(root)
    session.expire_all()
    episode = session.get(Episode, 1)
    assert (episode.key, episode.body) == ("種だけ", "")


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
    CommitEpisode({"story_id": story["id"], "start": "11572/03/25 00:00:00",
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


def test_episode_moves_with_its_txt_under_another_story(session, place, tmp_path):
    first = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    second = CommitStory({"name": "アルバ", "place_id": place}).run()
    CommitEpisode({"story_id": first["id"], "start": "11572/03/25 00:00:00",
                   "title": "白い灯り", "text": "一話"}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    moved = os.path.join(root, "story", "2_アルバ")
    for name in ("1_11572-03-25-0000_白い灯り.md", "1_11572-03-25-0000_白い灯り.txt"):
        os.rename(os.path.join(root, STORY_DIR, name), os.path.join(moved, name))
    sync_db(root)

    session.expire_all()
    assert session.get(Episode, 1).story_id == second["id"]
    assert session.get(Episode, 1).body == "一話" and session.query(EpisodeText).count() == 1
    assert sorted(os.listdir(moved)) == [
        "0_アルバ.md", "2_11572-03-25-0000_白い灯り.md", "2_11572-03-25-0000_白い灯り.txt"]


def test_txt_without_an_episode_md_is_registered_with_an_empty_episode(session, place, tmp_path):
    story = CommitStory({"name": "遥かなる幻想郷まで", "place_id": place}).run()
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, os.path.join(STORY_DIR, "メモ.txt"), "覚え書き\n")
    result = sync_db(root)

    assert result["imported"] == {"episode": 1, "episode_text": 1}
    session.expire_all()
    episode = session.query(Episode).one()
    assert (episode.story_id, episode.title, episode.key, episode.start) == (story["id"], "メモ", "", None)
    assert episode.body == "覚え書き"
    assert sorted(os.listdir(os.path.join(root, STORY_DIR))) == ["0_遥かなる幻想郷まで.md", "1__メモ.md", "1__メモ.txt"]


def test_txt_in_a_directory_without_a_story_md_is_registered_with_an_empty_story(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    sync_db(root)

    _write(root, os.path.join("story", "未定", "新作", "1_11600-01-01-0000_はじまり.txt"), "一話\n")
    result = sync_db(root)

    assert result["imported"] == {"story": 1, "episode": 1, "episode_text": 1}
    session.expire_all()
    story = session.query(Story).one()
    episode = session.query(Episode).one()
    assert (story.name, story.directory_path, story.narration, story.state, story.text) == ("新作", "未定", "", "", "")
    assert (episode.story_id, episode.title, str(episode.start)) == (story.id, "はじまり", "11600/01/01 00:00:00")
    assert episode.body == "一話"
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
    assert sorted([Episode(story_id=12, start=Stamp(2034, 5, 20), title="無断学習").markdown_name,
                   story.record_name]) == ["0_仮史：生成時代.md", "12_2034-05-20-0000_無断学習.md"]


def test_hand_made_story_directory_is_imported_with_its_episodes(session, place, tmp_path):
    root = str(tmp_path / "worlds")
    sync_db(root)
    _write(root, os.path.join("story", "未定", "新作", "0_新作.md"), "新作の筋書き\n")
    _write(root, os.path.join("story", "未定", "新作", "下書きの話.md"), "話の種\n")
    _write(root, os.path.join("story", "未定", "新作", "下書きの話.txt"), "話の本文\n")

    result = sync_db(root)

    assert result["imported"] == {"story": 1, "episode": 1, "episode_text": 1}
    session.expire_all()
    story = session.query(Story).one()
    episode = session.query(Episode).one()
    assert (story.name, story.text, story.directory_path) == ("新作", "新作の筋書き", "未定")
    assert (episode.story_id, episode.key, episode.body) == (story.id, "話の種", "話の本文")
    assert sorted(os.listdir(os.path.join(root, "story", "未定"))) == [f"{story.id}_新作"]
