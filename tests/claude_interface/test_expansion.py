"""世界の展開の記録・取り消し・食い違いと、一行ずつ足す入口・表をまたぐ検索。"""
import pytest

from data_access_logic.character.add_knower import AddKnower
from data_access_logic.character.append_history import AppendCharacterHistory
from data_access_logic.character.append_relation_history import AppendRelationHistory
from data_access_logic.character.record import CharacterHistoryRow, CharacterRelationHistoryRow
from data_access_logic.expansion.add_conflict import AddConflict
from data_access_logic.expansion.finish_expansion import FinishExpansion
from data_access_logic.expansion.form import (
    ConflictCreateForm, ConflictResolveForm, ExpansionCreateForm, ExpansionFinishForm,
)
from data_access_logic.expansion.list_expansions import ListExpansions
from data_access_logic.expansion.read_expansion import ReadExpansion
from data_access_logic.expansion.resolve_conflict import ResolveConflict
from data_access_logic.expansion.revert_expansion import RevertExpansion
from data_access_logic.expansion.start_expansion import StartExpansion
from data_access_logic.idea.append_history import AppendIdeaHistory
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.knowers import KnowerRow
from data_access_logic.location.append_history import AppendLocationHistory
from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.review.list_pending_reviews import ListPendingReviews
from data_access_logic.world.search_world import SearchWorld
from db.guard import ProtectedRowError
from db.schema import (
    Character, CharacterHistory, CharacterHistoryKnower, Event, LocationHistory, Meme, get_env_session,
)
from db.stamp import Stamp
from db.writer import writing


def _start(shown, **fields) -> int:
    return shown(StartExpansion(ExpansionCreateForm(mode="author", prompt="テストの一言", **fields)))["id"]


def test_start_and_finish_expansion(shown, world):
    expansion_id = _start(shown, story_id=world.story_id, time="1200/01/01")
    finished = shown(FinishExpansion(ExpansionFinishForm(id=expansion_id, summary="足した")))
    assert finished["status"] == "done" and finished["summary"] == "足した" and finished["time"] == "1200/01/01 00:00:00"
    with pytest.raises(ValueError):
        FinishExpansion(ExpansionFinishForm(id=expansion_id)).run()


def test_revert_expansion_undoes_adds_updates_and_deletes(shown, world):
    expansion_id = _start(shown)
    with get_env_session() as s, s.begin():
        removed = Meme(text="展開で消すAIのミーム")
        with writing("ai"):
            s.add(removed)
            s.flush()
        removed_id = removed.id
    with writing("ai", expansion_id):
        with get_env_session() as s, s.begin():
            added = Meme(text="展開で足すミーム")
            s.add(added)
            s.flush()
            added_id = added.id
            s.get_one(Meme, removed_id).text = "直した"
        with get_env_session() as s, s.begin():
            s.delete(s.get_one(Meme, removed_id))
        appended = shown(AppendCharacterHistory(
            character_id=world.character_ids[0],
            history=CharacterHistoryRow(start="1200/02/01", description="展開で足した来歴")))
    detail = shown(ReadExpansion(expansion_id=expansion_id))
    assert [(change["op"], change["table_name"]) for change in detail["changes"]] == [
        ("add", "meme"), ("update", "meme"), ("delete", "meme"),
        ("add", "character_history"), ("add", "character_history_knower")]

    result = shown(RevertExpansion(expansion_id=expansion_id))

    assert result == {"id": expansion_id, "reverted": 5}
    with get_env_session() as s:
        assert s.get(Meme, added_id) is None
        restored = s.get_one(Meme, removed_id)
        assert (restored.text, restored.origin) == ("展開で消すAIのミーム", "ai")
        assert s.get(CharacterHistory, appended["id"]) is None
    with pytest.raises(ValueError):
        RevertExpansion(expansion_id=expansion_id).run()


def test_revert_stops_when_a_row_was_changed_later(shown, world):
    expansion_id = _start(shown)
    with writing("ai", expansion_id), get_env_session() as s, s.begin():
        meme = Meme(text="あとで作者が直すミーム")
        s.add(meme)
        s.flush()
        meme_id = meme.id
    with get_env_session() as s, s.begin():
        s.get_one(Meme, meme_id).text = "作者が直した"
    with pytest.raises(ValueError, match="あとで直された"):
        RevertExpansion(expansion_id=expansion_id).run()
    with get_env_session() as s:
        assert s.get_one(Meme, meme_id).text == "作者が直した"


def test_conflicts_are_listed_for_the_author(shown, world):
    expansion_id = _start(shown)
    conflict = shown(AddConflict(ConflictCreateForm(
        expansion_id=expansion_id, table_name="character", row_id=world.character_ids[0],
        detail="来歴と一言が食い違う", proposal="来歴を直す")))
    reviews = shown(ListPendingReviews())
    assert any(review["key"] == f"conflict:{conflict['id']}" for review in reviews)
    assert shown(ListExpansions(limit=5))[0]["counts"]["open_conflicts"] >= 0

    shown(ResolveConflict(ConflictResolveForm(id=conflict["id"], status="dismissed")))

    assert not any(review["key"] == f"conflict:{conflict['id']}" for review in shown(ListPendingReviews()))


def test_conflicts_point_only_at_user_rows(shown, world):
    expansion_id = _start(shown)
    with writing("ai"), get_env_session() as s, s.begin():
        meme = Meme(text="AIのミーム")
        s.add(meme)
        s.flush()
        meme_id = meme.id
    with pytest.raises(ValueError, match="作者の行でない"):
        AddConflict(ConflictCreateForm(expansion_id=expansion_id, table_name="meme", row_id=meme_id,
                                       detail="食い違い")).run()


def test_append_entrances_add_one_row_without_touching_others(shown, world):
    character_id = world.character_ids[0]
    with get_env_session() as s:
        before = len(s.get_one(Character, character_id).histories)

    with writing("ai_append"):
        added = shown(AppendCharacterHistory(character_id=character_id, history=CharacterHistoryRow(
            start="1200/03/01", kind="記憶", description="港の火事を覚えている")))
        place = shown(AppendLocationHistory(location_id=world.location_id, history=LocationHistoryRow(
            start="1200/03/01", description="港で火事が起きる")))
        called = shown(AppendIdeaHistory(idea_id=world.idea_id, history=IdeaHistoryRow(
            start="1200", name="港の呼び名", knowers=[KnowerRow(knower_id=character_id)])))
        knower = shown(AddKnower(table="character_history", row_id=added["id"],
                                 knower=KnowerRow(knower_id=world.character_ids[1], start="1200/04/01")))
        relation = shown(AppendRelationHistory(character_relation_id=world.relation_id,
                                               history=CharacterRelationHistoryRow(start="1200", description="港で会う")))

    assert relation["table"] == "character_relation_history" and called["table"] == "idea_history"
    with get_env_session() as s:
        histories = s.get_one(Character, character_id).histories
        assert len(histories) == before + 1
        row = s.get_one(CharacterHistory, added["id"])
        assert row.origin == "ai"
        assert {knower.knower_id for knower in row.knowers} == set(world.character_ids)
        assert s.get_one(CharacterHistoryKnower, knower["id"]).start == Stamp.parse("1200/04/01")
        assert [knower.location_id for knower in s.get_one(LocationHistory, place["id"]).knowers] == [world.location_id]
    with pytest.raises(ValueError, match="もう入っている"):
        AddKnower(table="character_history", row_id=added["id"], knower=KnowerRow(knower_id=character_id)).run()


def test_append_writer_cannot_use_replacing_entrances(world):
    from data_access_logic.character.form import CharacterUpdateForm
    from data_access_logic.character.update_character import UpdateCharacter

    with pytest.raises(ProtectedRowError), writing("ai_append"):
        UpdateCharacter(CharacterUpdateForm(id=world.character_ids[0], histories=[])).run()


def test_search_world_finds_rows_across_tables(shown, world):
    with get_env_session() as s:
        character = s.get_one(Character, world.character_ids[0])
        event = s.get_one(Event, world.event_id)
        word = character.name
        event_name = event.name

    # テストを回すたびに同じ名前の行が増えるので、件数で切らない
    result = shown(SearchWorld(words=[word, event_name], story_id=world.story_id, limit_per_table=10**6))

    tables = {(hit["table"], hit["id"]) for hit in result["hits"]}
    assert ("character", world.character_ids[0]) in tables
    assert ("event", world.event_id) in tables
    hit = next(hit for hit in result["hits"] if hit["table"] == "character" and hit["id"] == world.character_ids[0])
    assert word in hit["words"] and hit["origin"] == "user"
    assert any(linked["table"] == "character" for linked in hit["linked"])


def test_ai_writer_can_commit_events_without_touching_user_memes(shown, world, mock_ai):
    """出来事の確定に続くミームの対づけ・種のまとめは、AI の書き手のあいだは作者のミーム・種を直さない。"""
    from data_access_logic.event.commit_event import CommitEvent
    from data_access_logic.event.form import EventCreateForm

    expansion_id = _start(shown)
    with get_env_session() as s:
        assert s.get_one(Meme, world.meme_id).anti_meme_id is None
    with writing("ai", expansion_id):
        record = CommitEvent(EventCreateForm(name="展開の出来事", time="1200/05/01", text="港で疫病が流行った",
                                             location_id=world.location_id)).run()
    assert isinstance(record, dict)
    with get_env_session() as s:
        assert s.get_one(Event, record["id"]).origin == "ai"
        assert s.get_one(Meme, world.meme_id).anti_meme_id is None
