import json

import pytest

from ai.claude_code.interface._base import UnknownFieldError, UnknownRecordError
from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from db.schema import Idea, Location


@pytest.fixture
def world(session):
    root = Location(name="世界線", kind="世界線", text="")
    session.add(root)
    session.commit()
    return root.id


def test_commit_from_json_string(session, world):
    draft = {"name": "外部デバイス", "kind": "技術", "location_id": world, "text": "身体アシスト技術"}
    result = CommitIdea(json.dumps(draft, ensure_ascii=False)).run()

    record = session.get(Idea, result["id"])
    assert record.name == "外部デバイス" and record.kind == "技術"
    assert record.location_id == world and record.text == "身体アシスト技術"

    child = CommitIdea({"name": "寄生型", "kind": "技術", "parent_idea_id": result["id"]}).run()
    assert session.get(Idea, child["id"]).parent_idea_id == result["id"]
    assert child["text"] == ""


@pytest.mark.parametrize("draft, message", [
    ({"kind": "技術"}, "name は必須"),
    ({"name": "アイデア"}, "kind は必須"),
])
def test_commit_requires_name_and_kind(session, draft, message):
    with pytest.raises(ValueError, match=message):
        CommitIdea(draft).run()
    assert session.query(Idea).count() == 0


def test_commit_finds_or_creates_the_classification_as_parent(session, world):
    world_idea = Idea(name="世界線", kind="世界線", text="", location_id=world)
    session.add(world_idea)
    session.commit()

    result = CommitIdea({"name": "外部デバイス", "kind": "技術", "location_id": world}).run()

    record = session.get(Idea, result["id"])
    classification = session.get(Idea, record.parent_idea_id)
    assert classification.name == "技術" and classification.kind == "技術"
    assert classification.parent_idea_id == world_idea.id

    # 続けて同じ kind のアイデアを足すと、同じ分類を再利用する(新しく作らない)
    second = CommitIdea({"name": "寄生型デバイス", "kind": "技術", "location_id": world}).run()
    assert session.get(Idea, second["id"]).parent_idea_id == classification.id
    assert session.query(Idea).filter_by(name="技術", kind="技術").count() == 1


def test_commit_respects_an_explicit_parent(session, world):
    world_idea = Idea(name="世界線", kind="世界線", text="", location_id=world)
    parent = Idea(name="親アイデア", kind="技術", text="", location_id=world)
    session.add_all([world_idea, parent])
    session.commit()

    result = CommitIdea(
        {"name": "外部デバイス", "kind": "技術", "location_id": world, "parent_idea_id": parent.id}).run()

    assert session.get(Idea, result["id"]).parent_idea_id == parent.id
    # 自動探索が余計な分類を作っていない
    assert session.query(Idea).filter_by(name="技術", kind="技術").count() == 0


def test_commit_does_not_seek_a_parent_for_the_classification_itself(session, world):
    world_idea = Idea(name="世界線", kind="世界線", text="", location_id=world)
    session.add(world_idea)
    session.commit()

    result = CommitIdea({"name": "技術", "kind": "技術", "location_id": world}).run()

    assert session.get(Idea, result["id"]).parent_idea_id is None


def test_commit_rejects_unknown_references(session, world):
    with pytest.raises(UnknownRecordError, match="location_id=999"):
        CommitIdea({"name": "アイデア", "kind": "概念", "location_id": 999}).run()
    with pytest.raises(UnknownRecordError, match="parent_idea_id=999"):
        CommitIdea({"name": "アイデア", "kind": "概念", "parent_idea_id": 999}).run()
    with pytest.raises(UnknownFieldError):
        CommitIdea({"name": "アイデア", "kind": "概念", "read": "ご"}).run()
    assert session.query(Idea).count() == 0
