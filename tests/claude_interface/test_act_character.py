"""人物モード(`ActCharacter`)。人物の一手と、その結果を足すこと(足すことと end を入れることだけ)。"""
import pytest
from sqlalchemy import select

from data_access_logic.character.record import CharacterMove
from data_access_logic.expansion.act_character import ActCharacter
from data_access_logic.expansion.act_models import ActIdeaDraft, ActOutcomeDraft, IntentDraft, NewCharacterDraft
from data_access_logic.expansion.read_expansion import ReadExpansion
from data_access_logic.expansion.revert_expansion import RevertExpansion
from data_access_logic.flows import act
from db.schema import (
    Character, CharacterHistory, CharacterLocation, Event, Expansion, IdeaHistory, get_env_session,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


class ScriptedAI(MockAIClient):
    """人物の一手と、その裁きだけを決めた答えにする。人物の生成などほかの呼び出しはモックに任せる。"""

    def __init__(self, actor_id: int, destination_id: int, arc_id: int | None = None, arc_closed: bool = False):
        super().__init__(seed=0)
        self.actor_id = actor_id
        self.destination_id = destination_id
        self.arc_id = arc_id
        self.arc_closed = arc_closed

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is IntentDraft:
            self.calls.append({"prompt": prompt, "system": system, "style_scope": style_scope})
            return IntentDraft(inner="港の病人を放っておけない", aim="村に診療所を開く", action="村へ移って診療所を開く",
                               speech="ここで診ます", arc_id=self.arc_id,
                               new_arc_name=None if self.arc_id is not None else "診療所を開く")
        if output is ActOutcomeDraft:
            self.calls.append({"prompt": prompt, "system": system, "style_scope": style_scope})
            return ActOutcomeDraft(
                event_name="診療所の開業", event_text="村の空き家を借りて診療所を開いた", character_ids=[self.actor_id],
                character_moves=[CharacterMove(character_id=self.actor_id, location_id=self.destination_id)],
                character_updates=[], location_abolished=False, location_founded=None, event_duration_days=3,
                ideas=[ActIdeaDraft(keyword="潮風療法", kind="技術", description="潮風に当てて熱を下げる手当て",
                                    called="潮風の手当て", detail="熱が下がると村人は信じている", knower_ids=[self.actor_id])],
                new_characters=[NewCharacterDraft(description="診療所で雇われた若い助手", person=True, relation="雇い人")],
                arc_closed=self.arc_closed)
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_act_character_adds_rows_and_records_the_expansion(world):
    actor_id = world.character_ids[1]
    ai = ScriptedAI(actor_id, world.neighbor_id)

    acted = act.act_character(character_id=actor_id, time="1200/05/01", seed=1, ai=ai)

    assert acted.actor.character_id == actor_id and acted.actor.location_id == world.location_id
    assert acted.arc_id is not None and acted.event.name == "診療所の開業"
    # 人物の目には、作者だけが読む筋書きを渡さない
    intent_prompt = ai.calls[0]["prompt"]
    assert "あなたが知っていること" in intent_prompt
    with get_env_session() as s:
        expansion = s.get_one(Expansion, acted.expansion_id)
        assert (expansion.mode, expansion.status, expansion.actor_id) == ("character", "done", actor_id)
        assert "村に診療所を開く" in expansion.prompt
        event = s.get_one(Event, acted.event.id)
        arc = s.get_one(Event, acted.arc_id)
        assert (event.origin, event.parent_event_id, arc.end) == ("ai", arc.id, None)
        rows = s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == actor_id)
                         .order_by(CharacterLocation.id)).all()
        assert rows[0].end == Stamp.parse("1200/05/01") and rows[0].origin == "user"
        assert (rows[-1].location_id, rows[-1].origin) == (world.neighbor_id, "ai")
        called = s.scalars(select(IdeaHistory).where(IdeaHistory.name == "潮風の手当て")
                           .order_by(IdeaHistory.id.desc())).first()
        assert called is not None and [knower.knower_id for knower in called.knowers] == [actor_id]
        assert s.get_one(Character, actor_id).origin == "user"
    detail = ReadExpansion(expansion_id=acted.expansion_id).run()
    assert isinstance(detail, dict)
    assert {change["op"] for change in detail["changes"]} <= {"add", "update"}


def test_act_character_continues_and_closes_an_arc(world):
    actor_id = world.character_ids[1]
    first = act.act_character(character_id=actor_id, time="1200/05/01", seed=1,
                              ai=ScriptedAI(actor_id, world.neighbor_id))
    second = act.act_character(character_id=actor_id, time="1200/06/01", seed=2,
                               ai=ScriptedAI(actor_id, world.location_id, arc_id=first.arc_id, arc_closed=True))

    assert second.arc_id == first.arc_id
    with get_env_session() as s:
        assert s.get_one(Event, first.arc_id).end == Stamp.parse("1200/06/01")
        assert s.get_one(Event, second.event.id).parent_event_id == first.arc_id


def test_act_character_can_be_reverted(world):
    actor_id = world.character_ids[1]
    with get_env_session() as s:
        histories_before = len(s.get_one(Character, actor_id).histories)
    acted = act.act_character(character_id=actor_id, time="1200/05/01", seed=1,
                              ai=ScriptedAI(actor_id, world.neighbor_id))

    RevertExpansion(expansion_id=acted.expansion_id).run()

    with get_env_session() as s:
        assert s.get(Event, acted.event.id) is None
        rows = s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == actor_id)).all()
        assert [row.end for row in rows] == [None]
        assert len(s.scalars(select(CharacterHistory).where(CharacterHistory.character_id == actor_id)).all()) \
            == histories_before


def test_act_character_picks_a_sub_character(world):
    actor_id = world.character_ids[1]
    acted = act.act_character(time="1200/05/01", seed=3, ai=ScriptedAI(actor_id, world.neighbor_id))
    with get_env_session() as s:
        assert s.get_one(Character, acted.actor.character_id).main_character is False


def test_act_character_entrance_is_registered():
    from gui.api import interface

    assert interface.entrance_class("expansion.act_character.ActCharacter") is ActCharacter


def test_failed_act_marks_the_expansion_failed(world):
    class Silent(MockAIClient):
        def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
            return None

    with pytest.raises(ValueError, match="一手が得られなかった"):
        act.act_character(character_id=world.character_ids[1], time="1200/05/01", ai=Silent())
    with get_env_session() as s:
        latest = s.scalars(select(Expansion).order_by(Expansion.id.desc())).first()
        assert latest is not None and latest.status == "failed"
