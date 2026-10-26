"""書き手(`db/writer.py`)ごとの守りと、展開の中で変えた行の記録(`db/guard.py`)。"""
import pytest
from sqlalchemy import delete, select

from db.guard import ProtectedRowError
from db.schema import (
    Character, CharacterHistory, CharacterLocation, Expansion, ExpansionChange, Meme, Story,
    get_env_session,
)
from db.stamp import Stamp
from db.writer import generated, writing


def _ai_meme(text: str) -> int:
    with writing("ai"), get_env_session() as s, s.begin():
        meme = Meme(text=text)
        s.add(meme)
        s.flush()
        return meme.id


def test_new_rows_take_the_writer_as_origin(world):
    meme_id = _ai_meme("AI のミーム")
    with get_env_session() as s:
        assert s.get_one(Meme, meme_id).origin == "ai"
        assert s.get_one(Meme, world.meme_id).origin == "user"


def test_rows_added_in_generated_flows_are_ai():
    with generated(), get_env_session() as s, s.begin():
        meme = Meme(text="生成で足したミーム")
        s.add(meme)
        s.flush()
        assert meme.origin == "ai"


def test_ai_cannot_change_or_delete_user_rows(world):
    with pytest.raises(ProtectedRowError), writing("ai"), get_env_session() as s, s.begin():
        s.get_one(Character, world.character_ids[0]).text = "AI が書き換える"
    with pytest.raises(ProtectedRowError), writing("ai"), get_env_session() as s, s.begin():
        s.delete(s.get_one(Meme, world.meme_id))
    with get_env_session() as s:
        assert s.get_one(Character, world.character_ids[0]).text != "AI が書き換える"


def test_ai_can_change_and_delete_ai_rows():
    meme_id = _ai_meme("直すミーム")
    with writing("ai"), get_env_session() as s, s.begin():
        s.get_one(Meme, meme_id).text = "直したミーム"
    with writing("ai"), get_env_session() as s, s.begin():
        s.delete(s.get_one(Meme, meme_id))
    with get_env_session() as s:
        assert s.get(Meme, meme_id) is None


def test_ai_cannot_write_stories():
    with pytest.raises(ProtectedRowError), writing("ai"), get_env_session() as s, s.begin():
        s.add(Story(name="AI の作品", text="筋"))


def test_ai_cannot_bulk_delete_user_rows(world):
    with pytest.raises(ProtectedRowError), writing("ai"), get_env_session() as s, s.begin():
        s.execute(delete(Meme).where(Meme.id == world.meme_id))


def test_ai_may_add_children_to_user_rows(world):
    character_id = world.character_ids[0]
    with writing("ai"), get_env_session() as s, s.begin():
        character = s.get_one(Character, character_id)
        character.histories = [*character.histories,
                               CharacterHistory(start=Stamp.parse("1200"), description="AI が足した来歴")]
    with get_env_session() as s:
        added = s.scalars(select(CharacterHistory).where(
            CharacterHistory.character_id == character_id, CharacterHistory.description == "AI が足した来歴")).one()
        assert added.origin == "ai"
        assert s.get_one(Character, character_id).origin == "user"


def test_append_writer_only_adds_and_sets_empty_end(world):
    character_id = world.character_ids[0]
    with writing("ai_append"), get_env_session() as s, s.begin():
        location = s.get_one(CharacterLocation, world.character_location_id)
        assert location.end is None
        location.end = Stamp.parse("1500")
    with pytest.raises(ProtectedRowError), writing("ai_append"), get_env_session() as s, s.begin():
        s.get_one(CharacterLocation, world.character_location_id).end = Stamp.parse("1600")
    with pytest.raises(ProtectedRowError), writing("ai_append"), get_env_session() as s, s.begin():
        s.get_one(Character, character_id).text = "書き換える"
    with pytest.raises(ProtectedRowError), writing("ai_append"), get_env_session() as s, s.begin():
        s.get_one(Character, character_id).histories = []
    meme_id = _ai_meme("人物モードでも消せないミーム")
    with pytest.raises(ProtectedRowError), writing("ai_append"), get_env_session() as s, s.begin():
        s.delete(s.get_one(Meme, meme_id))


def test_append_writer_cannot_end_before_start(world):
    with get_env_session() as s, s.begin():
        location = s.get_one(CharacterLocation, world.character_location_id)
        location.start = Stamp.parse("1300")
    with pytest.raises(ProtectedRowError), writing("ai_append"), get_env_session() as s, s.begin():
        s.get_one(CharacterLocation, world.character_location_id).end = Stamp.parse("1200")


def test_user_edit_makes_ai_row_the_users():
    meme_id = _ai_meme("作者が直すミーム")
    with generated(), get_env_session() as s, s.begin():
        s.get_one(Meme, meme_id).category = "信条"
    with get_env_session() as s:
        assert s.get_one(Meme, meme_id).origin == "ai"
    with get_env_session() as s, s.begin():
        s.get_one(Meme, meme_id).text = "作者が直した"
    with get_env_session() as s:
        assert s.get_one(Meme, meme_id).origin == "user"


def test_origin_is_not_taken_from_input(world):
    with get_env_session() as s, s.begin():
        s.get_one(Meme, world.meme_id).origin = "ai"
    with get_env_session() as s:
        assert s.get_one(Meme, world.meme_id).origin == "user"


def test_changes_in_an_expansion_are_recorded(world):
    with get_env_session() as s, s.begin():
        expansion = Expansion(mode="author", prompt="記録の確かめ")
        s.add(expansion)
        s.flush()
        expansion_id = expansion.id
    with writing("ai", expansion_id), get_env_session() as s, s.begin():
        meme = Meme(text="記録するミーム")
        s.add(meme)
        s.flush()
        meme.text = "直した"
        s.flush()
        s.delete(meme)
        s.flush()
        meme_id = meme.id
    with get_env_session() as s:
        changes = s.scalars(select(ExpansionChange).where(ExpansionChange.expansion_id == expansion_id)
                            .order_by(ExpansionChange.id)).all()
        assert [(change.op, change.table_name, change.row_id) for change in changes] == [
            ("add", "meme", meme_id), ("update", "meme", meme_id), ("delete", "meme", meme_id)]
        assert changes[1].before is not None and changes[1].before["text"] == "記録するミーム"
        assert changes[2].before is not None and changes[2].before["text"] == "直した"


def test_orphaned_children_are_guarded(world):
    """来歴の配列をまるごと置き換える入口を AI が呼んでも、外れた作者の行は消せない。"""
    character_id = world.character_ids[0]
    with get_env_session() as s:
        assert s.get_one(Character, character_id).histories, "テストの人物に来歴が無い"
    with pytest.raises(ProtectedRowError), writing("ai"), get_env_session() as s, s.begin():
        s.get_one(Character, character_id).histories = []
    with get_env_session() as s:
        assert s.get_one(Character, character_id).histories
