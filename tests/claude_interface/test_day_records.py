"""人物モードの一日の記録を、毎日行として積まずに整理して入れる(続いている出来事を延ばす・最近の思いの強さを直す)。"""
import pytest
from sqlalchemy import select

from data_access_logic.character.motivations import apply_changes
from data_access_logic.character.record import MotivationChange
from data_access_logic.expansion.act_models import DayOutcomeDraft, DaySaveForm
from data_access_logic.expansion.acting import continuing_events, save_day
from db.guard import ProtectedRowError
from db.schema import CharacterMotivation, Event, EventCharacter, get_env_session
from db.stamp import Stamp
from db.writer import Writer, writing

_DAY1, _DAY2, _DAY3 = (Stamp.parse(f"1201/03/0{day}") for day in (1, 2, 3))


def _outcome(text: str, continues: int | None = None, ids: list[int] | None = None) -> DayOutcomeDraft:
    return DayOutcomeDraft(event_name="空き地で待つ日々", event_text=text, character_ids=ids or [],
                           character_moves=[], nuance_changes=[], ideas=[], new_characters=[], motivation_changes=[],
                           continues_event_id=continues)


def _save(world, outcome: DayOutcomeDraft, time: Stamp, end: Stamp, participant_ids: list[int]) -> int:
    with get_env_session() as s, s.begin(), writing(Writer.AI_APPEND):
        saved = save_day(s, DaySaveForm(actor_id=world.character_ids[0], time=time, end=end,
                                        location_id=world.location_id, participant_ids=participant_ids,
                                        destinations=[], outcome=outcome))
        return saved.event.id


def test_a_repeated_day_extends_the_continuing_event(world):
    taro, hanako = world.character_ids
    first = _save(world, _outcome("空き地で子どもを待った"), _DAY1, _DAY2, [])
    with get_env_session() as s:
        assert [event.id for event in continuing_events(s, taro, _DAY2, None)] == [first]
        # 前の日に終わっていない出来事だけ(その日より後に始まる・前の日で切れた出来事は続けない)
        assert continuing_events(s, taro, _DAY3, None) == []

    second = _save(world, _outcome("空き地で子どもを待つ日が続いた。二日目は花子が来た", continues=first, ids=[hanako]),
                   _DAY2, _DAY3, [hanako])

    assert second == first
    with get_env_session() as s:
        event = s.get_one(Event, first)
        assert (event.time, event.end) == (_DAY1, _DAY3)
        assert event.text == "空き地で子どもを待つ日が続いた。二日目は花子が来た"
        linked = s.scalars(select(EventCharacter.character_id).where(EventCharacter.event_id == first)).all()
        assert sorted(linked) == sorted([taro, hanako])


def test_ai_append_cannot_rewrite_an_author_event(world):
    with get_env_session() as s, s.begin(), writing(Writer.AI_APPEND):
        event = s.get_one(Event, world.event_id)
        event.text = "書き換え"
        with pytest.raises(ProtectedRowError):
            s.flush()


def test_recent_ai_motivation_changes_strength_in_place(world):
    taro = world.character_ids[0]
    with get_env_session() as s, s.begin(), writing(Writer.AI_APPEND):
        [row] = apply_changes(s, [MotivationChange(character_id=taro, motivation_id=None, strength=2, text="空き地へ通いたい")],
                              [taro], _DAY1)
        row_id = row.id
    with get_env_session() as s, s.begin(), writing(Writer.AI_APPEND):
        # 生まれて数日のうちの揺れは、行を積まずに強さを直す
        apply_changes(s, [MotivationChange(character_id=taro, motivation_id=row_id, strength=3, text=None)], [taro], _DAY3)
    with get_env_session() as s:
        rows = s.scalars(select(CharacterMotivation).where(CharacterMotivation.character_id == taro,
                                                           CharacterMotivation.text == "空き地へ通いたい")).all()
        assert [(row.id, row.strength, row.end) for row in rows] == [(row_id, 3, None)]
    later = Stamp.parse("1201/04/01")
    with get_env_session() as s, s.begin(), writing(Writer.AI_APPEND):
        # 日がたってからの変化は、前の行を終えて新しい行を足す
        apply_changes(s, [MotivationChange(character_id=taro, motivation_id=row_id, strength=4, text=None)], [taro], later)
    with get_env_session() as s:
        rows = s.scalars(select(CharacterMotivation).where(CharacterMotivation.character_id == taro,
                                                           CharacterMotivation.text == "空き地へ通いたい")
                         .order_by(CharacterMotivation.start)).all()
        assert [(row.strength, row.end) for row in rows] == [(3, later), (4, None)]
