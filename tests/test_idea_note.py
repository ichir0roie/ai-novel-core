"""アイデアの本文に時代ごとに積む追記(`IdeaNote` / `resolve_idea_text`)。"""
import pytest

from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from ai.claude_code.interface.randomizer.update_idea import UpdateIdea
from data_access_logic.query import dictionary_query
from db.schema import Idea, IdeaNote, Location, resolve_idea_text
from db.schema_pydantic import to_dict
from db.stamp import Stamp


def _note(id_, start=None, end=None, text=""):
    return IdeaNote(id=id_, start=Stamp.parse(start), end=Stamp.parse(end), text=text)


# ---------------------------------------------------------------- resolve_idea_text

def test_no_notes_leaves_base_text_as_is():
    assert resolve_idea_text("基本の説明", []) == "基本の説明"
    assert resolve_idea_text("基本の説明", [], Stamp(150)) == "基本の説明"


def test_note_without_start_or_end_always_applies():
    notes = [_note(1, text="いつでも効く追記")]
    for time in (None, Stamp(1), Stamp(99999)):
        assert resolve_idea_text("基本", notes, time) == "基本\nいつでも効く追記"


def test_notes_fold_in_start_order_up_to_the_time():
    notes = [
        _note(1, start="200", text="200年、改良された"),
        _note(2, start="100", text="100年、発見された"),
    ]
    assert resolve_idea_text("基本の説明", notes, Stamp(50)) == "基本の説明"
    assert resolve_idea_text("基本の説明", notes, Stamp(100)) == "基本の説明\n100年、発見された"
    assert resolve_idea_text("基本の説明", notes, Stamp(200)) == (
        "基本の説明\n100年、発見された\n200年、改良された")


def test_note_stops_applying_from_its_end():
    notes = [_note(1, start="100", end="200", text="一時的な追記")]
    assert resolve_idea_text("基本", notes, Stamp(150)) == "基本\n一時的な追記"
    # end の時刻からは効かない
    assert resolve_idea_text("基本", notes, Stamp(200)) == "基本"


def test_without_time_only_notes_covering_every_time_apply():
    notes = [_note(1, text="全期間"), _note(2, start="100", text="始まりだけ")]
    assert resolve_idea_text("基本", notes, None) == "基本\n全期間"


# ---------------------------------------------------------------- CommitIdea / UpdateIdea

@pytest.fixture
def world(session):
    root = Location(name="世界線", kind="世界線", text="")
    session.add(root)
    session.commit()
    return root.id


def test_commit_idea_with_notes(session, world):
    result = CommitIdea({
        "name": "外部デバイス", "kind": "技術", "location_id": world, "text": "基本の説明",
        "notes": [{"start": "100", "text": "100年、実用化した"}],
    }).run()

    record = session.get(Idea, result["id"])
    assert [n.text for n in record.notes] == ["100年、実用化した"]
    assert Stamp.parse(result["notes"][0]["start"]) == Stamp(100)
    assert result["notes"][0]["end"] is None
    assert record.text_at(Stamp(150)) == "基本の説明\n100年、実用化した"


def test_commit_idea_rejects_bad_note_shape(session, world):
    with pytest.raises(ValueError, match="配列で渡す"):
        CommitIdea({"name": "アイデア", "kind": "概念", "notes": {"text": "x"}}).run()
    with pytest.raises(ValueError, match="スキーマに無い欄"):
        CommitIdea({"name": "アイデア", "kind": "概念", "notes": [{"unknown": "x"}]}).run()
    assert session.query(Idea).count() == 0


def test_update_idea_replaces_notes(session, world):
    created = CommitIdea({"name": "アイデア", "kind": "概念", "text": "基本", "location_id": world,
                          "notes": [{"start": "100", "text": "最初の追記"}]}).run()
    ids = [n.id for n in session.get(Idea, created["id"]).notes]

    UpdateIdea({"id": created["id"], "notes": [
        {"start": "100", "text": "書き換えた追記"},
        {"start": "200", "text": "後で足した追記"},
    ]}).run()

    session.expire_all()
    record = session.get(Idea, created["id"])
    # 同じ位置の行は使い回す(並びを変えなければ id は変わらない)
    assert [n.id for n in record.notes][:1] == ids
    assert [n.text for n in record.notes] == ["書き換えた追記", "後で足した追記"]


def test_update_idea_without_notes_keeps_existing_notes(session, world):
    created = CommitIdea({"name": "アイデア", "kind": "概念", "text": "基本", "location_id": world,
                          "notes": [{"start": "100", "text": "追記"}]}).run()

    UpdateIdea({"id": created["id"], "text": "直した"}).run()

    session.expire_all()
    record = session.get(Idea, created["id"])
    assert record.text == "直した"
    assert [n.text for n in record.notes] == ["追記"]


# ---------------------------------------------------------------- to_dict / GUI 往復

def test_to_dict_exposes_notes_without_id_or_idea_id(session, world):
    session.add(Idea(id=501, name="装置", kind="技術", location_id=world, text="基本の説明", notes=[
        IdeaNote(start=Stamp(100), text="100年、実用化した"),
    ]))
    session.commit()

    data = to_dict(session.get(Idea, 501))

    assert [(item["start"], item["end"], item["text"]) for item in data["notes"]] == [
        ("100/01/01 00:00:00", None, "100年、実用化した")]
    assert "id" not in data["notes"][0] and "idea_id" not in data["notes"][0]

    # GUI が渡す形(`to_dict` の出力をそのまま UpdateIdea へ返す)で追記を足せる
    data["notes"].append({"start": "200", "text": "200年、改良された"})
    UpdateIdea({"id": 501, "notes": data["notes"]}).run()

    session.expire_all()
    record = session.get(Idea, 501)
    assert [n.text for n in record.notes] == ["100年、実用化した", "200年、改良された"]
    assert record.text_at(Stamp(250)) == "基本の説明\n100年、実用化した\n200年、改良された"


# ---------------------------------------------------------------- 検索(select outer join)

def test_ideas_by_terms_matches_note_text_via_outer_join(session, world):
    matched = Idea(name="装置", kind="技術", location_id=world, text="基本の説明",
                   notes=[IdeaNote(start=Stamp(100), text="改良版には触媒を使う")])
    unrelated = Idea(name="別のもの", kind="技術", location_id=world, text="関係ない説明")
    session.add_all([matched, unrelated])
    session.commit()

    rows = session.scalars(dictionary_query.ideas_by_terms_select(["触媒"], time=Stamp(150))).all()
    assert [row.id for row in rows] == [matched.id]

    # その時刻にまだ効いていない追記には当たらない
    assert session.scalars(dictionary_query.ideas_by_terms_select(["触媒"], time=Stamp(50))).all() == []

    # 追記の無いアイデアも、基本の本文で当たれば外部結合で漏れない
    rows = session.scalars(dictionary_query.ideas_by_terms_select(["説明"], time=Stamp(150))).all()
    assert {row.id for row in rows} == {matched.id, unrelated.id}


def test_ideas_by_terms_does_not_duplicate_for_multiple_matching_notes(session, world):
    idea = Idea(name="装置", kind="技術", location_id=world, text="基本",
               notes=[IdeaNote(text="触媒その一"), IdeaNote(text="触媒その二")])
    session.add(idea)
    session.commit()

    rows = session.scalars(dictionary_query.ideas_by_terms_select(["触媒"])).all()
    assert [row.id for row in rows] == [idea.id]
