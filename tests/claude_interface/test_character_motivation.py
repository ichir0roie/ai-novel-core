"""人物のモチベーション(`character_motivation`)の入口。"""
import pytest
from pydantic import ValidationError

from data_access_logic.character.commit_character_motivation import CommitCharacterMotivation
from data_access_logic.character.delete_character_motivation import DeleteCharacterMotivation
from data_access_logic.character.form import CharacterMotivationCreateForm, CharacterMotivationUpdateForm
from data_access_logic.character.list_character_motivations import ListCharacterMotivations
from data_access_logic.character.update_character_motivation import UpdateCharacterMotivation
from db.schema import CharacterMotivation, get_env_session


def _commit(character_id: int, start: str, strength: int, text: str, end: str | None = None) -> dict:
    record = CommitCharacterMotivation(CharacterMotivationCreateForm(
        character_id=character_id, start=start, end=end, strength=strength, text=text)).run()
    assert isinstance(record, dict)
    return record


def test_commit_list_update_delete(world):
    character_id = world.character_ids[1]
    weak = _commit(character_id, "1199/01/01", 2, "静かに暮らしたい")
    strong = _commit(character_id, "1199/06/01", 5, "港の病人を救いたい")
    ended = _commit(character_id, "1198/01/01", 3, "終わった思い", end="1199/01/01")

    assert (strong["start"], strong["end"], strong["origin"]) == ("1199/06/01 00:00:00", None, "user")
    # 時刻を渡せば、その時刻に効いている行を強い順に
    assert [row["id"] for row in ListCharacterMotivations(character_id, time="1200/01/01").run()] \
        == [strong["id"], weak["id"]]
    # 省けば、すべての行を始まりの新しい順に
    assert [row["id"] for row in ListCharacterMotivations(character_id).run()] \
        == [strong["id"], weak["id"], ended["id"]]

    updated = UpdateCharacterMotivation(CharacterMotivationUpdateForm(id=weak["id"], strength=4, end="1200/02/01")).run()
    assert isinstance(updated, dict)
    assert (updated["strength"], updated["end"], updated["text"]) == (4, "1200/02/01 00:00:00", "静かに暮らしたい")

    DeleteCharacterMotivation(character_motivation_id=ended["id"]).run()
    with get_env_session() as s:
        assert s.get(CharacterMotivation, ended["id"]) is None


def test_rejects_out_of_range_strength_and_backward_span(world):
    character_id = world.character_ids[1]
    with pytest.raises(ValidationError):
        CharacterMotivationCreateForm(character_id=character_id, start="1200/01/01", strength=6, text="強すぎる")
    with pytest.raises(ValueError, match="start"):
        _commit(character_id, "1200/01/01", 3, "逆さの期間", end="1199/01/01")
    record = _commit(character_id, "1200/01/01", 3, "思い")
    with pytest.raises(ValueError, match="start"):
        UpdateCharacterMotivation(CharacterMotivationUpdateForm(id=record["id"], end="1200/01/01")).run()
    with pytest.raises(ValidationError):
        CharacterMotivationUpdateForm(id=record["id"], text=None)


def test_entrances_are_registered():
    from gui.api import interface

    for entrance in ("CommitCharacterMotivation", "UpdateCharacterMotivation", "DeleteCharacterMotivation",
                     "ListCharacterMotivations"):
        module = "".join(f"_{c.lower()}" if c.isupper() else c for c in entrance).lstrip("_")
        assert interface.entrance_class(f"character.{module}.{entrance}").__name__ == entrance
