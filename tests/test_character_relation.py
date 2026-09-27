import json

import pytest

from ai.claude_code.interface._base import UnknownFieldError, UnknownRecordError
from ai.claude_code.interface.randomizer.commit_character_relation import CommitCharacterRelation
from ai.claude_code.interface.randomizer.update_character_relation import UpdateCharacterRelation
from ai.claude_code.interface.world.list_character_relations import ListCharacterRelations
from db.schema import Character, CharacterRelation
from db.stamp import Stamp


@pytest.fixture
def people(session):
    rows = [Character(name="娘", kind="人物", text=""), Character(name="母", kind="人物", text=""),
            Character(name="裁きの座", kind="組織", text="")]
    session.add_all(rows)
    session.commit()
    return {"daughter": rows[0].id, "mother": rows[1].id, "court": rows[2].id}


def test_commit_and_list(session, people):
    result = CommitCharacterRelation(json.dumps({
        "character_id_1": people["mother"], "character_id_2": people["daughter"],
        "relation": "母", "start": "11572", "end": "11582",
        "text": "地上で十年を共に暮らす。"}, ensure_ascii=False)).run()
    assert result["relation"] == "母" and result["id"] is not None
    assert result["start"] == "11572/01/01 00:00:00" and result["end"] == "11582/01/01 00:00:00"
    CommitCharacterRelation({"character_id_1": people["court"], "character_id_2": people["mother"],
                             "relation": "所属先"}).run()

    record = session.get(CharacterRelation, result["id"])
    assert (record.character_id_1, record.character_id_2) == (people["mother"], people["daughter"])
    assert record.text == "地上で十年を共に暮らす。"
    assert record.start == Stamp(11572) and record.end == Stamp(11582)

    rows = ListCharacterRelations().run()
    assert [r["relation"] for r in rows] == ["母", "所属先"]
    rows = ListCharacterRelations(people["daughter"]).run()
    assert [r["relation"] for r in rows] == ["母"]
    assert ListCharacterRelations(people["court"]).run()[0]["text"] == ""


def test_commit_rejects_bad_input(session, people):
    base = {"character_id_1": people["mother"], "character_id_2": people["daughter"], "relation": "母"}
    with pytest.raises(ValueError, match="relation は必須"):
        CommitCharacterRelation({**base, "relation": ""}).run()
    with pytest.raises(ValueError, match="別の人物"):
        CommitCharacterRelation({**base, "character_id_2": people["mother"]}).run()
    with pytest.raises(UnknownRecordError):
        CommitCharacterRelation({**base, "character_id_2": 9999}).run()
    with pytest.raises(UnknownFieldError):
        CommitCharacterRelation({**base, "strength": 3}).run()
    assert session.query(CharacterRelation).count() == 0


def test_update(session, people):
    created = CommitCharacterRelation({"character_id_1": people["mother"], "character_id_2": people["daughter"],
                                       "relation": "母"}).run()
    result = UpdateCharacterRelation({"id": created["id"], "relation": "生みの母", "text": "本文"}).run()
    assert result["relation"] == "生みの母"
    session.expire_all()
    assert session.get(CharacterRelation, created["id"]).text == "本文"

    with pytest.raises(ValueError, match="id は必須"):
        UpdateCharacterRelation({"relation": "x"}).run()
    with pytest.raises(ValueError, match="見つからない"):
        UpdateCharacterRelation({"id": 9999, "relation": "x"}).run()
    with pytest.raises(ValueError, match="別の人物"):
        UpdateCharacterRelation({"id": created["id"], "character_id_2": people["mother"]}).run()
