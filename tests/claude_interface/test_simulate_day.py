"""人物モード(`SimulateDay`)。人物たちの一日を一時間ずつ動かし、行動の表に残して、人物ごとの一日を出来事一件にまとめること。
詳細の場所にいない人物は動かさないこと、作者の予定の時間は予定で埋めること、眠気・空腹の規則、取り消し。"""
import json

from sqlalchemy import select

from data_access_logic import constants
from data_access_logic.character.record import MotivationChange
from data_access_logic.event.progress_models import CharacterUpdateDraft
from data_access_logic.expansion import budget
from data_access_logic.expansion.act_models import (
    ActIdeaDraft, DayOutcomeDraft, HourDraft, ImpactFrame, Needs, ReactionDraft,
)
from data_access_logic.expansion.revert_expansion import RevertExpansion
from data_access_logic.expansion.simulate_day import SimulateDay
from data_access_logic.flows import act
from data_access_logic.query import expansion_query
from db.schema import (
    Character, CharacterLocation, CharacterMotivation, Episode, EpisodeCharacter, Event, EventAction, EventCharacter,
    Expansion, IdeaHistory, Location, get_env_session,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient

_DAY = "1200/05/01"


def _stamp(value: str) -> Stamp:
    stamp = Stamp.parse(value)
    assert stamp is not None
    return stamp


def _detail_places(world) -> tuple[int, int]:
    """都(エリア)の下に、詳細の場所(家と市場)を足して、二人の住まいを家に移す。"""
    with get_env_session() as s:
        home = Location(name="テストの家", kind="家", text="二人の家", parent_id=world.location_id, map_detail=True,
                        start="1150")
        market = Location(name="テストの市場", kind="市場", text="都の市場", parent_id=world.location_id, map_detail=True,
                          start="1150")
        s.add_all([home, market])
        s.flush()
        for character_id in world.character_ids:
            for row in s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == character_id)).all():
                row.end = _stamp("1199/01/01")
            s.add(CharacterLocation(character_id=character_id, location_id=home.id, start="1199/01/01"))
        s.commit()
        return home.id, market.id


class ScriptedAI(MockAIClient):
    """一時間ごとの手・居合わせた相手への応じ・一日の記録だけを決めた答えにする。"""

    def __init__(self, market_id: int, motivation_changes: list[MotivationChange] | None = None):
        super().__init__(seed=0)
        self.market_id = market_id
        self.motivation_changes = motivation_changes or []

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        call = {"output": output, "prompt": prompt, "system": system, "model": model, "effort": effort}
        if output is HourDraft:
            self.calls.append(call)
            hungry = "おなかがすいた" in prompt
            return HourDraft(kind="食べる" if hungry else "用事", location_id=self.market_id,
                             action="市場でパンを買って食べる" if hungry else "市場で野菜を並べる",
                             speech="いい天気だね", thought="今日も忙しい")
        if output is ReactionDraft:
            self.calls.append(call)
            return ReactionDraft(action="隣の人にうなずき返す", speech="そうだね", thought="顔見知りだ")
        if output is DayOutcomeDraft:
            self.calls.append(call)
            request = json.loads(prompt.rsplit("\n", 1)[0])
            ids = [person["人物id"] for person in request["居合わせた人物"]]
            return DayOutcomeDraft(
                event_name="市場の一日", event_text="朝から市場で野菜を並べ、隣の人と話した", character_ids=ids,
                character_moves=[], character_updates=[CharacterUpdateDraft(character_id=ids[0], text="【名前】は働き者だ")],
                ideas=[ActIdeaDraft(keyword="朝市の値札", kind="制度", description="朝市で値を札に書いて出す決まり",
                                    called="値札", detail="値札があると安心だと皆が言う", knower_ids=ids)],
                new_characters=[], motivation_changes=self.motivation_changes)
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)

    def calls_of(self, output) -> list[dict]:
        return [call for call in self.calls if call.get("output") is output]


def _actions(character_id: int) -> list[EventAction]:
    with get_env_session() as s:
        return list(s.scalars(select(EventAction).where(EventAction.character_id == character_id)
                              .order_by(EventAction.time)).all())


def test_two_people_spend_a_day_hour_by_hour_and_meet_at_the_market(world):
    home_id, market_id = _detail_places(world)
    ai = ScriptedAI(market_id)

    run = act.simulate_day(world.character_ids, _DAY, seed=1, ai=ai)

    assert not run.failed, run.failed
    assert sorted(acted.character_id for acted in run.acted) == sorted(world.character_ids)
    for acted in run.acted:
        actions = _actions(acted.character_id)
        # 一日 24 時間を一時間ずつ残す
        assert len(actions) == 24 == acted.actions
        assert actions[0].time == _stamp(_DAY) and actions[-1].time == _stamp(f"{_DAY} 23:00:00")
        # 夜中は眠っているので、人物の目には聞かずに眠る
        assert actions[0].kind == "眠る" and actions[0].location_id == home_id
        assert {action.expansion_id for action in actions} == {acted.expansion_id}
        assert {action.origin for action in actions} == {"ai"}
        # 起きてからは市場へ出て、もう一人と居合わせて応じ合う
        awake = [action for action in actions if action.kind != "眠る"]
        assert awake and all(action.location_id == market_id for action in awake)
        assert any("隣の人にうなずき返す" in action.text for action in awake)
        assert any(action.kind == "食べる" for action in awake)
        other_id = next(id_ for id_ in world.character_ids if id_ != acted.character_id)
        assert acted.met_ids == [other_id]
        with get_env_session() as s:
            event = s.get_one(Event, acted.event.id)
            assert (event.name, event.origin, event.location_id) == ("市場の一日", "ai", market_id)
            assert event.time == awake[0].time and event.end == _stamp("1200/05/02")
            linked = s.scalars(select(EventCharacter.character_id).where(EventCharacter.event_id == event.id)).all()
            assert set(linked) == set(world.character_ids)
            expansion = s.get_one(Expansion, acted.expansion_id)
            assert (expansion.mode, expansion.status, expansion.actor_id) == ("character", "done", acted.character_id)
            assert act.MET_HEAD in expansion.prompt
    # 眠っている時間は人物の目に聞かないので、一人につき一日の時間より少ない
    assert 0 < len(ai.calls_of(HourDraft)) < 2 * 24
    assert ai.calls_of(ReactionDraft)
    hour_call = ai.calls_of(HourDraft)[0]
    # 人物の目には年の数を渡さず、知っていることと行ける場所を渡す
    assert "1200/" not in hour_call["prompt"] and "あなたが知っていること" in hour_call["prompt"]
    assert "テストの市場" in hour_call["prompt"] and "体の具合" in hour_call["prompt"]
    assert (hour_call["model"], hour_call["effort"]) == (constants.ACT_MODEL, constants.ACT_EFFORT)
    judge_call = ai.calls_of(DayOutcomeDraft)[0]
    assert (judge_call["model"], judge_call["effort"]) == (constants.ACT_JUDGE_MODEL, constants.ACT_JUDGE_EFFORT)
    assert "その日の行動(起きた順)" in judge_call["prompt"]
    with get_env_session() as s:
        called = s.scalars(select(IdeaHistory).where(IdeaHistory.name == "値札").order_by(IdeaHistory.id.desc())).first()
        assert called is not None and called.origin == "ai"


def test_people_outside_detail_places_are_not_moved(world):
    """詳細の場所にいない人物は、一日を動かさない(わけを添えて失敗にする)。"""
    ai = ScriptedAI(world.location_id)

    run = act.simulate_day(world.character_ids, _DAY, ai=ai)

    assert not run.acted and len(run.failed) == 2
    assert all("詳細の場所でない" in failure.error for failure in run.failed)
    assert not ai.calls and not _actions(world.character_ids[0])


def test_hours_of_an_author_event_are_filled_with_the_plan(world):
    """作者の出来事の予定がある時間は、予定の場所で予定のことをしていることにし、人物の目には聞かない。"""
    home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    with get_env_session() as s:
        tea = Event(name="テストの茶会", text="家で茶会を開く", time=f"{_DAY} 10:00:00", end=f"{_DAY} 12:00:00",
                    location_id=home_id, event_characters=[EventCharacter(character_id=actor_id)])
        s.add(tea)
        s.commit()
        tea_id = tea.id

    act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))

    fixed = [action for action in _actions(actor_id) if action.fixed_event_id == tea_id]
    assert [action.time for action in fixed] == [_stamp(f"{_DAY} 10:00:00"), _stamp(f"{_DAY} 11:00:00")]
    assert all(action.kind == "予定" and action.location_id == home_id for action in fixed)


def test_a_day_is_moved_only_once_and_can_be_reverted(world):
    _home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    first = act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))
    acted = first.acted[0]

    again = act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))

    assert not again.acted and "もう動かしてある" in again.failed[0].error
    RevertExpansion(expansion_id=acted.expansion_id).run()
    assert not _actions(actor_id)
    with get_env_session() as s:
        assert s.get(Event, acted.event.id) is None


def test_the_next_day_carries_over_the_needs(world):
    """前の日の最後の一時間の眠気・空腹を引き継ぐ。日を省けば、人物が最後に出た日の翌日を動かす。"""
    _home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))
    last = _actions(actor_id)[-1]

    run = act.simulate_day([actor_id], None, seed=2, ai=ScriptedAI(market_id))

    assert run.date is not None and _stamp(str(run.date)) == _stamp("1200/05/02")
    first = [action for action in _actions(actor_id) if action.time >= _stamp("1200/05/02")][0]
    carried = Needs(sleepiness=last.sleepiness, hunger=last.hunger, asleep=last.kind == "眠る")
    expected = act.next_needs(carried, first.kind, 24)
    assert (first.sleepiness, first.hunger) == (expected.sleepiness, expected.hunger)


def test_motivations_move_with_the_day_and_a_stronger_one_is_not_moved(world):
    """一日の記録の増減で思いが動く。太郎は花子より影響力が上なので、花子の一日では思いを書かれない。"""
    _home_id, market_id = _detail_places(world)
    actor_id, main_id = world.character_ids[1], world.character_ids[0]
    with get_env_session() as s:
        cure = CharacterMotivation(character_id=actor_id, start="1199/01/01", strength=4, text="市場で店を持ちたい")
        s.add(cure)
        s.commit()
        cure_id = cure.id
    changes = [MotivationChange(character_id=actor_id, motivation_id=cure_id, strength=5, text=None),
               MotivationChange(character_id=main_id, motivation_id=None, strength=2, text="花子を手伝いたい")]

    run = act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id, changes))

    acted = run.acted[0]
    assert [(row.text, row.strength) for row in acted.motivations] == [("市場で店を持ちたい", 5)]
    with get_env_session() as s:
        assert s.get_one(CharacterMotivation, cure_id).end is not None
        assert not s.scalars(select(CharacterMotivation).where(CharacterMotivation.character_id == main_id)).all()


def test_next_needs_follow_sleep_and_meals():
    awake = act.next_needs(Needs(sleepiness=50, hunger=50), "用事", 24)
    assert (awake.sleepiness, awake.hunger, awake.asleep) == (56, 62, False)
    asleep = act.next_needs(Needs(sleepiness=50, hunger=50), "眠る", 24)
    assert (asleep.sleepiness, asleep.asleep) == (38, True)
    assert act.next_needs(Needs(sleepiness=50, hunger=90), "食べる", 24).hunger == 0
    # 一日 30 時間の暦では、一時間の増え方を減らして一日あたりの量をそろえる
    assert act.next_needs(Needs(sleepiness=0, hunger=0), "用事", 30).hunger == round(12 * 24 / 30)
    assert act.next_needs(Needs(sleepiness=99, hunger=99), "用事", 24).sleepiness == 100


def test_clamp_keeps_the_actor_first_and_cuts_the_rest():
    outcome = DayOutcomeDraft(
        event_name="x", event_text="x", character_ids=[1, 2, 3], character_moves=[],
        character_updates=[CharacterUpdateDraft(character_id=id_, text="t") for id_ in (3, 2, 1)],
        ideas=[], new_characters=[], motivation_changes=[])
    frame = ImpactFrame(influence="低", people=2, moves=1, new_characters=0, ideas=1, resistant_ids=[2])

    clamped = budget.clamp(outcome, frame, actor_id=1)

    assert [update.character_id for update in clamped.character_updates] == [1, 3]


def test_simulate_day_entrance_is_registered():
    from gui.api import interface

    assert interface.entrance_class("expansion.simulate_day.SimulateDay") is SimulateDay


def test_a_left_behind_character_moves_to_the_present_of_its_own_story(world):
    """作品の世界の今(本文のある最新の話)から ACT_STALE_DAYS 日より前に取り残された人物は、世界の今に寄せる。
    作品の無い人物は寄せない(ほかの作品の今に引っぱられない)。"""
    actor_id, other_id = world.character_ids[1], world.character_ids[0]
    with get_env_session() as s:
        s.get_one(Character, actor_id).story_id = world.story_id
        s.add(Episode(story_id=world.story_id, title="テスト後の話", plot_text="ずっと後", main_text="ずっと後の本文。",
                      start="1200/12/01 09:00:00", location_id=world.location_id,
                      episode_characters=[EpisodeCharacter(character_id=other_id)]))
        s.commit()

    with get_env_session() as s:
        assert expansion_query.last_appearance(s, actor_id) == _stamp("1200/12/01 09:00:00")
        s.get_one(Character, actor_id).story_id = None
        s.flush()
        assert expansion_query.last_appearance(s, actor_id) == _stamp("1200/04/01 18:00:00")
        s.rollback()
