"""人物モード(`SimulateDay`)。人物たちの一日を一時間ずつ、人物ごとの会話一つで動かし、行動の表に残して、人物ごとの一日を出来事一件に
まとめること。詳細の場所にいない人物は動かさないこと、作者の予定の時間は予定で埋めること、眠り・欲・行動量の決まりと日ごとの記録、取り消し。"""
import json

import pytest

from sqlalchemy import select

from data_access_logic import constants
from data_access_logic.character.record import MotivationChange
from data_access_logic.event.progress_models import CharacterUpdateDraft
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.expansion import budget, needs
from data_access_logic.expansion.act_models import (
    ActIdeaDraft, DayOutcomeDraft, HourDraft, ImpactFrame, NeedProfile, Needs, ReactionDraft,
)
from data_access_logic.expansion.revert_expansion import RevertExpansion
from data_access_logic.expansion.simulate_day import SimulateDay
from data_access_logic.flows import act
from data_access_logic.query import expansion_query
from db.schema import (
    Character, CharacterDay, CharacterLocation, CharacterMotivation, CharacterParameter, Episode, EpisodeCharacter, Event,
    EventAction, EventCharacter, Expansion, IdeaHistory, Location, get_env_session,
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
            return HourDraft(kind="食べる" if hungry else "働く", location_id=self.market_id,
                             action="市場でパンを買って食べる" if hungry else "市場で野菜を並べる",
                             speech="いい天気だね", thought="今日も忙しい",
                             deeds=["外に出た"] if hungry else ["外に出た", "働いた", "空を飛んだ"])
        if output is ReactionDraft:
            self.calls.append(call)
            return ReactionDraft(action="隣の人にうなずき返す", speech="そうだね", thought="顔見知りだ", deeds=[])
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
        # 夜中は眠っているので、人物の会話には聞かずに眠る。行動量に余裕があるので、8 時より一時間早く 7 時に起きる
        assert [action.kind for action in actions[:7]] == ["眠る"] * 7 and actions[7].kind != "眠る"
        assert actions[0].location_id == home_id
        assert {action.expansion_id for action in actions} == {acted.expansion_id}
        assert {action.origin for action in actions} == {"ai"}
        # 起きてからは市場へ出て、もう一人と居合わせて応じ合う
        awake = [action for action in actions if action.kind != "眠る"]
        assert awake and all(action.location_id == market_id for action in awake)
        assert any("隣の人にうなずき返す" in action.text for action in awake)
        assert any(action.kind == "食べる" for action in awake)
        # 行動量は、その一時間の行いのうち一番重いもの(知らない行いは数えない)
        assert {action.load for action in awake} == {1, 3}
        with get_env_session() as s:
            day = s.scalars(select(CharacterDay).where(CharacterDay.character_id == acted.character_id)).one()
            assert (day.expansion_id, day.date, day.load) == (acted.expansion_id, _stamp(_DAY), sum(a.load for a in awake))
            # 7 時間しか眠れなかった(要る眠りは 8 時間)。日付が変わってから眠る
            assert (day.sleep, day.bedtime) == (88, 25)
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
    # 人物一人に会話一つ。眠っている時間は会話に聞かないので、一人につき一日の時間より少ない
    # (起きている 17 時間の手と、居合わせた相手への応じが 17 回。どちらも同じ会話で問う)
    assert [session.asked for session in ai.sessions] == [34, 34]
    assert len(ai.calls_of(HourDraft)) == 2 * 17
    assert ai.calls_of(ReactionDraft)
    # 一時間ずつ二人が並んで問うので、三つ目の問いは二度目の問い
    first, second = ai.calls_of(HourDraft)[0], ai.calls_of(HourDraft)[2]
    # 一度目の問いには知っていることと行ける場所を渡し、二度目からは一時間の様子の差分だけを渡す。どちらにも年の数を渡さない
    assert "1200/" not in first["prompt"] and "あなたが知っていること" in first["prompt"]
    assert "テストの市場" in first["prompt"] and "体の具合" in first["prompt"]
    assert "過ぎた時間にしていたこと" in first["prompt"] and "眠っていた" in first["prompt"]
    assert "あなたが知っていること" not in second["prompt"] and "体の具合" in second["prompt"]
    assert (first["model"], first["effort"]) == (constants.ACT_MODEL, constants.ACT_EFFORT)
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


def test_the_next_day_follows_the_night_and_the_shortage(world):
    """前の日に日付が変わってから眠った人物は、その時刻まで起きていて、要る眠りと、前の日の不足の一部を眠ってから起きる。
    前の日の最後の一時間の空腹を引き継ぐ。日を省けば、人物が最後に出た日の翌日を動かす。"""
    _home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))
    last = _actions(actor_id)[-1]

    run = act.simulate_day([actor_id], None, seed=2, ai=ScriptedAI(market_id))

    assert run.date is not None and _stamp(str(run.date)) == _stamp("1200/05/02")
    second = [action for action in _actions(actor_id) if action.time >= _stamp("1200/05/02")]
    # 前の夜は 1 時に眠り、要る 8 時間と不足の取り戻し 1 時間から、行動量に余裕があって早起きする 1 時間を引いて 9 時に起きる
    assert second[0].kind != "眠る" and [action.kind for action in second[1:9]] == ["眠る"] * 8
    assert second[9].kind != "眠る"
    assert second[0].hunger == 0 if second[0].kind == "食べる" else second[0].hunger > last.hunger


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


def _profile(**values) -> NeedProfile:
    base = dict(appetite="並", sleep_drive="並", libido="並", required_sleep=8, prev_bed=0, wake=8, bed=24)
    return NeedProfile(**{**base, **values})


def test_sleep_plan_follows_the_drive_the_shortage_and_eagerness():
    # 並の睡眠欲なら、24 時に寝て 8 時に起きる
    assert needs.sleep_plan(24, "並", 0, 0, 0) == (8, 8, 24)
    # 前の夜に 22 時に眠れば 6 時に起きる。睡眠欲が高ければ、長く眠り早く寝る
    assert needs.sleep_plan(24, "並", 0, -2, 0) == (8, 6, 24)
    assert needs.sleep_plan(24, "高", 0, 0, 0) == (9, 9, 23)
    # 眠りが 4 時間足りなければ、並は 2 時間(朝に 1 時間・夜に 1 時間)、低い睡眠欲は 1 時間(朝)だけ取り戻す
    assert needs.sleep_plan(24, "並", 4, 0, 0) == (8, 9, 23)
    assert needs.sleep_plan(24, "低", 4, 0, 0) == (6, 7, 26)
    # 強いモチベーション・行動量の余裕があれば、早く起きて遅く寝る
    assert needs.sleep_plan(24, "並", 0, 0, 2) == (8, 6, 26)
    # 一日 30 時間の暦では、同じ割合(一日の三分の一を眠る)にそろえる
    assert needs.sleep_plan(30, "並", 0, 0, 0) == (10, 10, 30)


def test_needs_grow_with_the_drive_and_yesterday_shortage():
    profile = _profile()
    awake = needs.next_needs(Needs(hunger=50, desire=50), "働く", 12, 24, profile)
    # 眠気は寝る時刻の間際に強まる(8 時に起きて 24 時に寝る人の 13 時は、まだ眠くない)
    assert (awake.hunger, awake.desire, awake.sleepiness) == (60, 53, 3)
    assert needs.next_needs(Needs(hunger=90, desire=50), "食べる", 12, 24, profile).hunger == 0
    assert needs.next_needs(Needs(hunger=50, desire=90), "触れ合う", 12, 24, profile).desire == 0
    # 人と話すと、人と触れ合いたい欲が少し減る
    assert needs.next_needs(Needs(hunger=50, desire=90), "話す", 12, 24, profile).desire == 63
    # 眠っているあいだは、空腹がゆっくり増える
    assert needs.next_needs(Needs(hunger=50, desire=0), "眠る", 2, 24, profile).hunger == 52
    # 前の日に食べ足りなかったぶん強く増え、性欲が無ければ増えない
    hungry = _profile(food_pressure=needs.pressure(50), libido="無")
    grown = needs.next_needs(Needs(hunger=0, desire=0), "働く", 12, 24, hungry)
    assert (grown.hunger, grown.desire) == (15, 0)
    # 一日 30 時間の暦では、一時間の増え方を減らして一日あたりの量をそろえる
    assert needs.next_needs(Needs(hunger=0, desire=0), "働く", 12, 30, profile).hunger == round(10 * 24 / 30)


def test_need_levels_come_from_the_age_unless_set():
    unset = CharacterParameterValues()
    assert needs.levels_of(unset, 10) == ("高", "高", "無")
    assert needs.levels_of(unset, 30) == ("並", "並", "並")
    assert needs.levels_of(unset, 70) == ("低", "低", "低")
    assert needs.levels_of(CharacterParameterValues(libido="必"), 10) == ("高", "高", "必")


def test_satisfaction_fatigue_and_motivation_steps():
    profile = _profile(load_before=60, load_max=140)
    assert needs.satisfaction([40, 60, 100], [0, 0, 0], 6, profile) == (60, 75, 100)
    assert needs.fatigue(profile, 10) == 50 and needs.rest_chance(50) == 0
    assert needs.rest_chance(80) == pytest.approx(0.5) and needs.rest_chance(120) == constants.DAY_REST_MAX_CHANCE
    assert [needs.motivation_strength(total) for total in (100, 120, 300, 600)] == [0, 2, 3, 5]
    assert needs.hour_load(["外に出た", "何かを傷つけた"]) == 4 and needs.hour_load([]) == 0


def test_last_night_and_bedtime_count_what_was_slept():
    # 前の日の 22 時に眠り、7 時まで眠った(段取りより長く眠った分も数える)。20 時に自分から眠り、そのまま日を終えた
    profile = _profile(prev_bed=-2, wake=6, bed=24)
    sleeping = [True] * 7 + [False] * 13 + [True] * 4
    assert needs.last_night(sleeping, profile) == 9
    assert needs.bedtime(sleeping, profile) == 20
    # 日付が変わってから眠る段取りで、日の終わりに起きていれば、段取りの時刻
    assert needs.bedtime([True] * 7 + [False] * 17, _profile(bed=25)) == 25
    # 日付が変わってから 1 時に眠った前の夜は、1 時から続けて眠った時間
    assert needs.last_night([False] + [True] * 8 + [False] * 15, _profile(prev_bed=1)) == 8


def test_a_week_of_short_sleep_makes_a_motivation_and_a_tired_one_rests(world):
    """さかのぼった七日の眠りの不足で、眠りたいモチベーションを持つ。行動量が上限にいる人物は、会話に聞かずに休みがちになる。"""
    _home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    with get_env_session() as s:
        s.add(CharacterParameter(character_id=actor_id, start="1199/01/01", proactivity="低"))
        for days in range(1, 7):
            s.add(CharacterDay(character_id=actor_id, date=_stamp(_DAY).plus_days(-days), food=100, sleep=40, touch=100,
                               load=20, bedtime=24))
        s.commit()
    ai = ScriptedAI(market_id)

    run = act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    acted = run.acted[0]
    with get_env_session() as s:
        wanted = s.scalars(select(CharacterMotivation).where(
            CharacterMotivation.character_id == actor_id, CharacterMotivation.text == "ゆっくり眠りたい")).one()
        assert (wanted.strength, wanted.start, wanted.origin) == (4, _stamp(_DAY), "ai")
    # 前の日に 5 時間足りなかったので 3 時間を取り戻し、朝は 2 時間遅く 10 時に起きる(行動量に余裕が無いので早起きはしない)
    actions = _actions(actor_id)
    assert [action.kind for action in actions[:10]] == ["眠る"] * 10 and actions[10].kind != "眠る"
    # 七日の行動量が上限(七日 × 低の 18)の近くにいるので、休む時間が出る
    assert any(action.kind == "休む" for action in actions)
    assert acted.actions == 24
    RevertExpansion(expansion_id=acted.expansion_id).run()
    with get_env_session() as s:
        assert s.get(CharacterMotivation, wanted.id) is None


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
