import pytest

from ai.claude_code.interface._base import UnknownFieldError, UnknownRecordError
from ai.claude_code.interface.randomizer.delete_idea import DeleteIdea
from ai.claude_code.interface.randomizer.update_idea import UpdateIdea
from db.schema import Idea, Location


@pytest.fixture
def ideas(session):
    world = Location(name="世界線", kind="世界線", text="")
    session.add(world)
    session.flush()
    parent = Idea(name="崩壊時代", kind="時代", location_id=world.id, text="時代")
    session.add(parent)
    session.flush()
    child = Idea(name="崩壊年", kind="呼称", parent_idea_id=parent.id, text="呼称")
    session.add(child)
    session.commit()
    return {"world": world.id, "parent": parent.id, "child": child.id}


def test_update_changes_given_columns(session, ideas):
    result = UpdateIdea({"id": ideas["child"], "kind": "概念", "text": "直した"}).run()

    assert result["kind"] == "概念" and result["text"] == "直した"
    record = session.get(Idea, ideas["child"])
    assert record.name == "崩壊年" and record.parent_idea_id == ideas["parent"]


def test_update_repoints_parent(session, ideas):
    other = Idea(name="崩壊時代", kind="時代", text="時代")
    session.add(other)
    session.commit()

    UpdateIdea({"id": ideas["child"], "parent_idea_id": other.id}).run()
    assert session.get(Idea, ideas["child"]).parent_idea_id == other.id


def test_update_rejects_circular_parent(session, ideas):
    grandchild = Idea(name="崩壊記念日", kind="呼称", parent_idea_id=ideas["child"], text="呼称")
    session.add(grandchild)
    session.commit()

    with pytest.raises(ValueError, match="循環"):
        UpdateIdea({"id": ideas["parent"], "parent_idea_id": grandchild.id}).run()
    with pytest.raises(ValueError, match="循環"):
        UpdateIdea({"id": ideas["parent"], "parent_idea_id": ideas["child"]}).run()
    session.expire_all()
    assert session.get(Idea, ideas["parent"]).parent_idea_id is None


def test_update_rejects_bad_input(session, ideas):
    with pytest.raises(ValueError, match="id は必須"):
        UpdateIdea({"kind": "概念"}).run()
    with pytest.raises(ValueError, match="id=999"):
        UpdateIdea({"id": 999, "kind": "概念"}).run()
    with pytest.raises(UnknownRecordError, match="parent_idea_id=999"):
        UpdateIdea({"id": ideas["child"], "parent_idea_id": 999}).run()
    with pytest.raises(ValueError, match="自分自身"):
        UpdateIdea({"id": ideas["child"], "parent_idea_id": ideas["child"]}).run()
    with pytest.raises(UnknownFieldError):
        UpdateIdea({"id": ideas["child"], "read": "ご"}).run()


def test_delete_removes_idea(session, ideas):
    data = DeleteIdea(ideas["child"]).run()

    assert data == {"id": ideas["child"], "name": "崩壊年", "kind": "呼称"}
    session.expire_all()
    assert session.get(Idea, ideas["child"]) is None
    assert session.get(Idea, ideas["parent"]) is not None


def test_delete_keeps_idea_with_children(session, ideas):
    with pytest.raises(ValueError, match="下位のアイデアが残っている"):
        DeleteIdea(ideas["parent"]).run()
    with pytest.raises(UnknownRecordError, match="idea_id=999"):
        DeleteIdea(999).run()
    session.expire_all()
    assert session.get(Idea, ideas["parent"]) is not None
