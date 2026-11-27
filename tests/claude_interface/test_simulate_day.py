"""人物モード(`SimulateDay`)。人物たちの一日を一時間ずつ、人物ごとの会話一つで動かし、行動の表に残して、人物ごとの一日を出来事一件に
まとめること。詳細の場所にいない人物は動かさないこと、作者の予定の時間は予定で埋めること、眠り・欲・行動量の決まりと日ごとの記録、取り消し。"""
import json
import re
from types import SimpleNamespace
from unittest import mock

import pytest

from sqlalchemy import select

from data_access_logic import constants
from data_access_logic.character.record import MotivationChange
from data_access_logic.event.progress_models import NuanceChangeDraft
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.expansion import acting, budget, needs
from data_access_logic.expansion.act_models import (
    ActIdeaDraft, DayOutcomeDraft, DayPlace, HourDraft, HourScene, ImpactFrame, NeedProfile, Needs, PeopleForm, ResponseDraft,
)
from data_access_logic.expansion.draft_routines import DraftRoutines
from data_access_logic.expansion.revert_expansion import RevertExpansion
from data_access_logic.expansion.routines import RoutineCharacter, RoutineDraft, RoutineDraftRow, usable_rows
from data_access_logic.expansion.simulate_day import SimulateDay
from data_access_logic.flows import act
from data_access_logic.query import expansion_query, world_creation_query
from db.schema import (
    Character, CharacterDay, CharacterHistory, CharacterLocation, CharacterMotivation, CharacterNuance, CharacterParameter,
    CharacterRoutine, Episode,
    EpisodeCharacter, Event, EventAction, EventCharacter, Expansion, IdeaHistory, Location, get_env_session,
)
from db.stamp import Calendar, Stamp, using_calendar
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


def _present_ids(prompt: str) -> list[int]:
    """問いの「目の前にいる人物」の人物id(手は、目の前の人物みなに働きかける)。"""
    return [person["人物id"] for person in json.loads(prompt.rsplit("\n", 1)[0]).get("目の前にいる人物", [])]


# 応じる問いも出力の形は HourDraft なので、問いの見出しで見分けて控える
REACTION = "応じる問い"


def _reaction(prompt: str) -> bool:
    return "居合わせた人物がこの一時間にしたこと" in prompt


class ScriptedAI(MockAIClient):
    """一時間ごとの手・居合わせた相手への応じ・一日の記録だけを決めた答えにする。"""

    def __init__(self, market_id: int, motivation_changes: list[MotivationChange] | None = None):
        super().__init__(seed=0)
        self.market_id = market_id
        self.motivation_changes = motivation_changes or []
        # 人物ごとの、この一時間に決めた種別(応じても変わらなければ、決めていた種別を返す)
        self.kinds: dict[str, str] = {}

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        call = {"output": output, "prompt": prompt, "system": system, "model": model, "effort": effort}
        name = re.search(r"あなた\((.+?)\)", prompt)
        if output is HourDraft and _reaction(prompt):
            self.calls.append({**call, "output": REACTION})
            return HourDraft(hours=3, after_action="", kind=self.kinds.get(name.group(1) if name else "", "働く"), action="隣の人にうなずき返す",
                             next_location_id=self.market_id, toward_ids=[], thought="顔見知りだ", ate="なし", deeds=[])
        if output is HourDraft:
            self.calls.append(call)
            hungry = "おなかがすいた" in prompt
            if name:
                self.kinds[name.group(1)] = "食べる" if hungry else "働く"
            return HourDraft(hours=3, after_action="", kind="食べる" if hungry else "働く", next_location_id=self.market_id,
                             action="市場でパンを買って食べる" if hungry else "市場で野菜を並べる",
                             toward_ids=_present_ids(prompt), thought="今日も忙しい",
                             ate="なし", deeds=["外に出た"] if hungry else ["外に出た", "働いた", "空を飛んだ"])
        if output is DayOutcomeDraft:
            self.calls.append(call)
            request = json.loads(prompt.rsplit("\n", 1)[0])
            ids = [person["人物id"] for person in request["居合わせた人物"]]
            return DayOutcomeDraft(
                event_name="市場の一日", event_text="朝から市場で野菜を並べ、隣の人と話した", character_ids=ids,
                character_moves=[], nuance_changes=[NuanceChangeDraft(
                    character_id=ids[0], kind="癖", situation="朝の市場で", text="誰より先に野菜を並べる")],
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
        # 起きた一時間は家で過ごし、そこで決めた次の場所(市場)へ移って、もう一人と居合わせる。台詞は残さない
        awake = [action for action in actions if action.kind != "眠る"]
        assert awake[0].location_id == home_id and all(action.location_id == market_id for action in awake[1:])
        assert all(action.speech is None for action in actions)
        # 先に動く一人目(影響力・行動量が同じなので id の順)だけが、後の人物に働きかけられて応じる
        first_mover = acted.character_id == min(world.character_ids)
        assert any("隣の人にうなずき返す" in action.text for action in awake) is first_mover
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
            # 人となりは来歴に足さず、癖の行にする(その日にしたことは出来事にだけ残る)
            assert not s.scalars(select(CharacterHistory).where(CharacterHistory.start == event.time,
                                                                CharacterHistory.character_id.in_(world.character_ids))).all()
            habits = s.scalars(select(CharacterNuance).where(CharacterNuance.start == event.time,
                                                             CharacterNuance.character_id.in_(world.character_ids))).all()
            assert habits and {(habit.kind, habit.situation, habit.origin) for habit in habits} == {("癖", "朝の市場で", "ai")}
            assert all(habit.text == "誰より先に野菜を並べる" for habit in habits)
            expansion = s.get_one(Expansion, acted.expansion_id)
            assert (expansion.mode, expansion.status, expansion.actor_id) == ("character", "done", acted.character_id)
            assert act.MET_HEAD in expansion.prompt
    # 人物一人に会話一つ。眠っている時間と、決めた手(働くは三時間)を続けている時間は会話に聞かないので、起きている 17 時間より
    # ずっと少ない(一人 9 回。先に動く一人目には、後の人物に働きかけられた応じが 9 回。どちらも同じ会話で問う)
    assert sorted(session.asked for session in ai.sessions) == [9, 18]
    assert len(ai.calls_of(HourDraft)) == 2 * 9
    assert len(ai.calls_of(REACTION)) == 9
    # 後に動く人物は、先の人物がこの一時間にしていることを見てから決める
    later = ai.calls_of(HourDraft)[1]["prompt"]
    assert "目の前の人物が、この一時間にしていること" in later and "市場で" in later.split("この一時間にしていること")[1]
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
    # 動いた人物が当事者の、前の出来事の名前を渡す(同じ名前の記録を続けて立てないように)
    judged = json.loads(judge_call["prompt"].rsplit("\n", 1)[0])
    assert "テスト市" in judged["動いた人物のこれまでの記録の名前(新しい順)"]
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
    # 種別が「食べる」でなくても、食べた量で空腹を戻す(話しながら料理をつまむ一時間で、空腹が増え続けない)
    assert needs.next_needs(Needs(hunger=80, desire=0), "話す", 20, 24, profile, ate="しっかり").hunger == 0
    assert needs.next_needs(Needs(hunger=80, desire=0), "話す", 20, 24, profile, ate="少し").hunger == 50
    assert needs.next_needs(Needs(hunger=80, desire=0), "話す", 20, 24, profile, ate="なし").hunger == 90


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
    # 疲れているので、眠りたい思いが強くても遅寝はせず、取り戻す分だけ早い 23 時までに寝床で眠る
    with get_env_session() as s:
        day = s.scalars(select(CharacterDay).where(CharacterDay.character_id == actor_id)
                        .order_by(CharacterDay.date.desc())).first()
        assert day is not None and day.bedtime <= 23
    assert (actions[-1].kind, actions[-1].location_id) == ("眠る", _home_id)
    assert acted.actions == 24
    RevertExpansion(expansion_id=acted.expansion_id).run()
    with get_env_session() as s:
        assert s.get(CharacterMotivation, wanted.id) is None


def test_clamp_keeps_the_actor_first_and_cuts_the_rest():
    outcome = DayOutcomeDraft(
        event_name="x", event_text="x", character_ids=[1, 2, 3], character_moves=[],
        nuance_changes=[NuanceChangeDraft(character_id=id_, kind="思い込み", text="t") for id_ in (3, 2, 1)],
        ideas=[], new_characters=[], motivation_changes=[])
    frame = ImpactFrame(influence="低", people=2, moves=1, new_characters=0, ideas=1, resistant_ids=[2])

    clamped = budget.clamp(outcome, frame, actor_id=1)

    assert [change.character_id for change in clamped.nuance_changes] == [1, 3]


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


def _clock_of(prompt: str) -> int:
    found = re.search(r'"時刻": "(\d+)時ごろ"', prompt)
    return int(found.group(1)) if found else -1


class BedtimeAI(ScriptedAI):
    """20 時までは市場で働き、20 時からは市場で眠ると答える。"""

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is HourDraft and _clock_of(prompt) >= 20:
            self.calls.append({"output": output, "prompt": prompt})
            return HourDraft(hours=3, after_action="", kind="眠る", next_location_id=self.market_id, action="眠くなったので横になる", toward_ids=[],
                             thought="もう寝よう", ate="なし", deeds=[])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_going_to_bed_late_keeps_the_character_asleep_at_home(world):
    """寝る時刻の三時間前より後に自分から眠ったら、寝床(住まい)で朝まで眠り、もう会話には聞かない。"""
    home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    ai = BedtimeAI(market_id)

    act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    actions = _actions(actor_id)
    # 20 時より後(夜)に眠ると答えたので、その一時間は市場で横になり、次の一時間から寝床で眠って、もう聞かない
    slept = next(index for index, action in enumerate(actions) if index >= 7 and action.kind == "眠る")
    assert slept >= 20 and actions[slept].location_id == market_id
    assert all((action.kind, action.location_id) == ("眠る", home_id) for action in actions[slept + 1:])
    assert _clock_of(ai.calls_of(HourDraft)[-1]["prompt"]) == slept


_LONG_DAY = Calendar(offset=(5000, 1, 1, 0, 0, 0), month_days=(31,) * 12, hours_per_day=30, days_per_week=6,
                     name="一日の長い暦")


def test_the_next_day_is_counted_in_the_calendar_of_the_day():
    """一日 30 時間の暦でも、次の日の 0 時は暦の次の日付(`Stamp.plus_days` の 24 時間では同じ日のうちになる)。"""
    with using_calendar(_LONG_DAY):
        assert str(acting.next_day_start(Stamp(1593, 4, 19))) == "1593/04/20 00:00:00"
        assert str(acting.next_day_start(Stamp(1593, 4, 31))) == "1593/05/01 00:00:00"
        assert str(acting.next_day_start(Stamp(1593, 12, 31))) == "1594/01/01 00:00:00"
    assert acting.next_day_start(_stamp("1200/05/01")) == _stamp("1200/05/02")


def test_an_hour_is_drafted_as_deeds_without_lines():
    """一時間の手は行いの粒で、台詞の欄を持たない。"""
    assert "speech" not in HourDraft.model_json_schema()["properties"]
    assert HourDraft(hours=3, after_action="", action="a", kind="走る", next_location_id=1, toward_ids=[], thought="", ate="なし", deeds=[]).kind == "そのほか"


class NightAI(ScriptedAI):
    """日中は市場で働き、時間帯が夜になったら眠ると答える。"""

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is HourDraft and '"時間帯": "夜"' in prompt:
            self.calls.append({"output": output, "prompt": prompt})
            return HourDraft(hours=3, after_action="", kind="眠る", next_location_id=self.market_id, action="早めに横になる", toward_ids=[],
                             thought="今日は疲れた", ate="なし", deeds=[])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_sleeping_in_the_evening_goes_to_bed_and_the_bedtime_is_told(world):
    """寝る時刻の三時間前より早くても、夜に自分から眠ったら床に就いたとして、もう会話に聞かない。床に就く目安は、日付をまたいでも、
    一度目の問いの予定と一時間ごとの様子で伝える。"""
    home_id, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    ai = NightAI(market_id)

    act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    actions = _actions(actor_id)
    # 夜(19 時から)に眠ると答えたので、寝る 25 時の三時間前より早くても、その一時間は市場で横になり、次の一時間から寝床で眠る
    slept = next(index for index, action in enumerate(actions) if index >= 7 and action.kind == "眠る")
    assert 19 <= slept < 22 and actions[slept].location_id == market_id
    assert all((action.kind, action.location_id) == ("眠る", home_id) for action in actions[slept + 1:])
    assert _clock_of(ai.calls_of(HourDraft)[-1]["prompt"]) == slept
    first = ai.calls_of(HourDraft)[0]["prompt"]
    assert "日付が変わって1時ごろ: 眠る" in first and '"床に就く目安まで": "あと18時間"' in first


class FollowAI(ScriptedAI):
    """後に動く人物(leader)は家から市場へ出かけ、先に動く人物は家で黙って休むと答える。先の人物は、出かける leader について市場へ行く。"""

    def __init__(self, market_id: int, home_id: int, leader: str):
        super().__init__(market_id)
        self.home_id = home_id
        self.leader = leader

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is HourDraft and _reaction(prompt):
            self.calls.append({"output": REACTION, "prompt": prompt})
            return HourDraft(hours=3, after_action="", kind="移動", action="あとについて市場へ行く", next_location_id=self.market_id, toward_ids=[],
                             thought="", ate="なし", deeds=["外に出た"])
        if output is HourDraft:
            self.calls.append({"output": output, "prompt": prompt})
            if f"あなた({self.leader})" in prompt:
                return HourDraft(hours=3, after_action="", kind="移動", next_location_id=self.market_id, action="市場へ出かける", toward_ids=[],
                                 thought="", ate="なし", deeds=["外に出た"])
            return HourDraft(hours=3, after_action="", kind="休む", next_location_id=self.home_id, action="家で休む", toward_ids=[], thought="", ate="なし",
                             deeds=[])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_a_companion_leaving_is_seen_and_can_be_followed(world):
    """一時間の始めに同じ場所にいた後の人物が場所を移るなら、先に決めた人物にも移る先が見え、応じてついていける。"""
    home_id, market_id = _detail_places(world)
    first_id, leader_id = sorted(world.character_ids)
    with get_env_session() as s:
        leader = s.get_one(Character, leader_id).name
    ai = FollowAI(market_id, home_id, leader)

    act.simulate_day(world.character_ids, _DAY, seed=1, ai=ai)

    follower = _actions(first_id)
    awake = [action for action in follower if action.kind != "眠る"]
    # 家で休むと決めたが、出かける leader を見て、次の一時間に市場へついていった
    assert awake[0].location_id == home_id and "あとについて市場へ行く" in awake[0].text
    assert awake[0].kind == "移動" and awake[1].location_id == market_id
    # 応じるのは先に決めて残った人物で、後に決めて出かける leader は応じない
    reaction = ai.calls_of(REACTION)[0]["prompt"]
    assert f"あなた({leader})" not in reaction and "(テストの市場へ移るところ)" in reaction


def test_a_newcomer_is_not_born_in_the_room_of_someone_present(world):
    """一日で現れる人物の生まれの場所は、居合わせた人物の住まいなら、その一つ上の場所にする。"""
    home_id, market_id = _detail_places(world)
    with get_env_session() as s:
        people = [s.get_one(Character, id_) for id_ in world.character_ids]
        assert acting._newcomer_location_id(s, home_id, people, _stamp(_DAY)) == world.location_id
        assert acting._newcomer_location_id(s, market_id, people, _stamp(_DAY)) == market_id


def test_a_long_day_tells_the_hour_in_a_24_hour_day_and_the_time_to_bed():
    """一日の長さが違う暦では、今の時刻に 24 時間の一日に直した時刻を添える(西暦では添えない)。床に就く目安までの時間も渡す。"""
    with using_calendar(_LONG_DAY):
        scene = HourScene(time=Stamp(1593, 1, 25, 24), location_id=1, needs=Needs(hunger=0, desire=0), fatigue=0,
                          meanwhile=[], present=[], seen=[], until_bed=6)
        told = scene.for_prompt([], set())
    assert told["いま"]["24時間の一日に直すと"] == "19時ごろ" and told["床に就く目安まで"] == "あと6時間"
    western = HourScene(time=_stamp("1200/05/01 23:00:00"), location_id=1, needs=Needs(hunger=0, desire=0), fatigue=0,
                        meanwhile=[], present=[], seen=[], until_bed=0, calendar=None).for_prompt([], set())
    assert "24時間の一日に直すと" not in western["いま"] and western["床に就く目安まで"] == "もう床に就く時刻"


def test_housemates_are_known_by_name_without_a_relation(world):
    """同じ住まいに住む人物は、関係の行が無くても名前を知っている相手に入る。"""
    home_id, _ = _detail_places(world)
    first, second = world.character_ids
    with get_env_session() as s:
        assert acting._housemate_ids(s, s.get_one(Character, first), _stamp(_DAY)) == [second]


class HomeFirstAI(ScriptedAI):
    """起きて最初の一時間は家で朝ごはんを食べ、そのあとは市場で働く。"""

    def __init__(self, market_id: int, home_id: int):
        super().__init__(market_id)
        self.home_id = home_id

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is HourDraft and not self.calls_of(HourDraft):
            self.calls.append({"output": output, "prompt": prompt})
            return HourDraft(hours=3, after_action="", kind="食べる", next_location_id=self.home_id, action="家で朝ごはんを食べる", toward_ids=[],
                             thought="", ate="なし", deeds=[])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_a_resident_not_moved_is_marked_staying_and_the_judge_learns_who_was_where(world):
    """動かしていない人物は、目の前にいても「ここで過ごしていて、ほかの場所へは一緒に行かない」と添える。記録する段には、
    居合わせた人物ごとの、動いた人物との間柄と居合わせた場所を渡す。"""
    home_id, market_id = _detail_places(world)
    actor_id, resident_id = world.character_ids
    ai = HomeFirstAI(market_id, home_id)

    act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    first = ai.calls_of(HourDraft)[0]["prompt"]
    assert f'"人物id": {resident_id}' in first and '"この一日": "ここで過ごしていて、ほかの場所へは一緒に行かない"' in first
    judge = json.loads(ai.calls_of(DayOutcomeDraft)[0]["prompt"].rsplit("\n", 1)[0])
    resident = next(person for person in judge["居合わせた人物"] if person["人物id"] == resident_id)
    assert resident["居合わせた場所"] == ["テストの家"]
    assert "動いた人物との間柄" in resident


def test_residents_not_moved_are_away_in_the_daytime():
    """動かしていない住人は、昼(24 に割って 9〜18 時の手前)は留守にしている。一日の長さが違う暦でも同じ割合。"""
    assert not acting._resident_away(_stamp("1200/05/01 08:00:00"))
    assert acting._resident_away(_stamp("1200/05/01 09:00:00"))
    assert acting._resident_away(_stamp("1200/05/01 17:00:00"))
    assert not acting._resident_away(_stamp("1200/05/01 18:00:00"))
    with using_calendar(_LONG_DAY):
        # 30 時間の暦の 11 時は 24 に割って 8.8 時、12 時は 9.6 時、23 時は 18.4 時
        assert not acting._resident_away(Stamp(1593, 1, 25, 11))
        assert acting._resident_away(Stamp(1593, 1, 25, 12))
        assert not acting._resident_away(Stamp(1593, 1, 25, 23))


def test_a_character_moved_earlier_is_seen_doing_what_was_recorded(world):
    """その日を先に動かした人物は、後から動かす人物の目の前に、行動の表のその一時間の場所と行いで出て、合わせては変わらない。
    後から動いた人物の一日の記録には、居合わせた人物として入る。"""
    _, market_id = _detail_places(world)
    earlier_id, later_id = sorted(world.character_ids)
    act.simulate_day([earlier_id], _DAY, seed=1, ai=ScriptedAI(market_id))
    recorded = {action.time: action for action in _actions(earlier_id)}
    ai = ScriptedAI(market_id)

    run = act.simulate_day([later_id], _DAY, seed=1, ai=ai)

    assert not run.failed, run.failed
    # 先の人物は会話がもう閉じているので、働きかけても応じない
    assert not ai.calls_of(REACTION)
    prompts = [json.loads(call["prompt"].rsplit("\n", 1)[0]) for call in ai.calls_of(HourDraft)]
    shown = [person for prompt in prompts for person in prompt["目の前にいる人物"] if person["人物id"] == earlier_id]
    assert shown and all(person["この一日"] == "この一日はもう決まっていて、あなたに合わせては変わらない" for person in shown)
    # 市場で一緒にいる一時間は、先の人物のその一時間の行い(眠っていれば「眠っている」)が見える
    noon = next(prompt for prompt in prompts if prompt["いま"].get("時刻") == "12時ごろ")
    earlier_noon = next(person for person in noon["目の前にいる人物"] if person["人物id"] == earlier_id)
    assert earlier_noon["この一時間にしていること"] == recorded[_stamp(f"{_DAY} 12:00:00")].text
    judge = json.loads(ai.calls_of(DayOutcomeDraft)[0]["prompt"].rsplit("\n", 1)[0])
    assert earlier_id in [person["人物id"] for person in judge["居合わせた人物"]]
    assert run.acted[0].met_ids == []


class StayHomeAI(ScriptedAI):
    """一日じゅう家で過ごす。"""

    def __init__(self, market_id: int, home_id: int):
        super().__init__(market_id)
        self.home_id = home_id

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is HourDraft:
            self.calls.append({"output": output, "prompt": prompt})
            return HourDraft(hours=3, after_action="", kind="休む", next_location_id=self.home_id, action="家で繕い物をする", toward_ids=[], thought="",
                             ate="なし", deeds=[])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_hours_an_earlier_character_spent_at_the_home_keep_the_resident_home(world):
    """先に動かした人物が住まいにいた起きている時間(住人が留守にする昼を除く)は、その人物の目に住人として出ていたので、
    後から動かす住人をその時間は住まいに縛る(予定と同じに埋める)。"""
    home_id, market_id = _detail_places(world)
    earlier_id, later_id = sorted(world.character_ids)
    act.simulate_day([earlier_id], _DAY, seed=1, ai=StayHomeAI(market_id, home_id))
    with get_env_session() as s:
        earlier_name = s.get_one(Character, earlier_id).name

    act.simulate_day([later_id], _DAY, seed=1, ai=ScriptedAI(market_id))

    later = {action.time.digits[3]: action for action in _actions(later_id)}
    # 朝(起きてから 9 時まで)と夕方から(18 時から)は住まいにいて、昼は市場へ出る
    assert later[8].kind == "予定" and later[8].location_id == home_id and str(earlier_name) in later[8].text
    assert later[12].kind != "予定" and later[12].location_id == market_id
    assert later[19].kind == "予定" and later[19].location_id == home_id


def test_a_resident_not_moved_stays_at_the_routine_place_in_its_hours(world):
    """動かしていない人物は、決まった居場所の行の時間はその場所にいて、していることが見える。期間に入る行があって時間に
    当たらなければ住まいにいる(昼の留守の決まりは使わない)。"""
    home_id, market_id = _detail_places(world)
    actor_id, resident_id = world.character_ids
    with get_env_session() as s:
        s.add(CharacterRoutine(character_id=resident_id, location_id=market_id, hour_from=10, hour_to=20,
                               text="野菜の屋台を開けている", start="1199/01/01"))
        s.commit()
    ai = ScriptedAI(market_id)

    act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    prompts = [json.loads(call["prompt"].rsplit("\n", 1)[0]) for call in ai.calls_of(HourDraft)]

    def resident_at(clock: str) -> dict | None:
        prompt = next(prompt for prompt in prompts if prompt["いま"].get("時刻") == clock)
        return next((person for person in prompt["目の前にいる人物"] if person["人物id"] == resident_id), None)

    # 起きた一時間は家、昼(住人の留守の時間)でも屋台の時間は市場にいる
    morning = resident_at("7時ごろ")
    assert morning is not None and "ここでしていること" not in morning
    noon = resident_at("12時ごろ")
    assert noon is not None and noon["ここでしていること"] == "野菜の屋台を開けている"
    assert resident_at("9時ごろ") is None
    judge = json.loads(ai.calls_of(DayOutcomeDraft)[0]["prompt"].rsplit("\n", 1)[0])
    assert any("(動かしていない人物): 野菜の屋台を開けている" in line for line in judge["その日の行動(起きた順)"])


class AnsweringAI(ScriptedAI):
    """働きかけられた動かしていない人物は、屋台の野菜をおまけして応じる。"""

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is ResponseDraft:
            self.calls.append({"output": output, "prompt": prompt, "system": system})
            return ResponseDraft(action="屋台の人参を一本おまけして渡す", thought="よく来る子だ")
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_a_resident_not_moved_answers_when_worked_on(world):
    """動いた人物が、目の前の動かしていない人物に働きかけると、その人物の会話(自分の材料と、働きかけてきた人物とそのしたこと)で
    応じ方を聞く。会話は人物ごとに一日一つで、材料は一度目にだけ渡す。応じたことは、動いた人物には次の一時間に見え、
    記録する段には「(動かしていない人物)が応じた」として渡る。"""
    _, market_id = _detail_places(world)
    actor_id, resident_id = world.character_ids
    with get_env_session() as s:
        s.add(CharacterRoutine(character_id=resident_id, location_id=market_id, hour_from=10, hour_to=20,
                               text="野菜の屋台を開けている", start="1199/01/01"))
        s.commit()
    ai = AnsweringAI(market_id)

    run = act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    assert not run.failed, run.failed
    answers = ai.calls_of(ResponseDraft)
    assert answers
    scenes = [json.loads(call["prompt"].rsplit("\n", 1)[0]) for call in answers]
    assert "あなたが知っていること" in scenes[0]
    # 朝は家で、昼は屋台で応じる
    assert scenes[0]["ここでしていること"] == "住まいで過ごしている"
    at_market = next(scene for scene in scenes if scene["いる場所"] == "テストの市場")
    assert at_market["ここでしていること"] == "野菜の屋台を開けている"
    assert at_market["働きかけてきた人物"]["人物id"] == actor_id
    assert at_market["働きかけてきた人物"]["あなたにしたこと"] == "市場で野菜を並べる"
    assert all("あなたが知っていること" not in call["prompt"] for call in answers[1:])
    # 応じる会話は人物ごとに一つ(動いた人物の会話と、動かしていない人物の会話)
    assert len([made for made in ai.sessions if made.asked]) == 2
    hours = [json.loads(call["prompt"].rsplit("\n", 1)[0]) for call in ai.calls_of(HourDraft)]
    assert any(any(line.endswith("屋台の人参を一本おまけして渡す") for line in hour["目の前の人物が、さっきしていたこと"])
               for hour in hours)
    judge = json.loads(ai.calls_of(DayOutcomeDraft)[0]["prompt"].rsplit("\n", 1)[0])
    assert any("(動かしていない人物)が応じた: 屋台の人参を一本おまけして渡す" in line
               for line in judge["その日の行動(起きた順)"])
    with get_env_session() as s:
        prompt = s.get_one(Expansion, run.acted[0].expansion_id).prompt
    assert act.MET_HEAD in prompt and "働きかけて、その場で応じてもらった" in prompt


def test_a_day_that_continued_an_earlier_event_counts_as_the_last_appearance(world):
    """前の日の出来事を延ばして続けた日は、出来事の始まりが前の日のままでも、行動の表の時刻で最後に出た日に数える
    (数えないと、日を省いた次の回が同じ日をもう一度選ぶ)。"""
    _, market_id = _detail_places(world)
    actor_id = world.character_ids[0]
    run = act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))
    with get_env_session() as s:
        # 前の日に始まった出来事を延ばした形にする
        s.get_one(Event, run.acted[0].event.id).time = _stamp("1200/04/30 07:00:00")
        s.commit()
        last = expansion_query.last_appearance(s, actor_id)
    assert last is not None and last.digits[:3] == (1200, 5, 1)


class RoutineAI(MockAIClient):
    """朝と昼に同じ屋台の行と、同じ時間帯の二つ目の行と、行ける場所の外の行を返す。"""

    def __init__(self, market_id: int):
        super().__init__(seed=0)
        self.market_id = market_id

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is RoutineDraft:
            self.calls.append({"output": output, "prompt": prompt, "system": system})
            return RoutineDraft(routines=[
                RoutineDraftRow(period="朝", location_id=self.market_id, text="野菜の屋台を開けている"),
                RoutineDraftRow(period="昼", location_id=self.market_id, text="野菜の屋台を開けている"),
                RoutineDraftRow(period="昼", location_id=self.market_id, text="同じ時間帯の二つ目"),
                RoutineDraftRow(period="夜", location_id=-1, text="行けない場所"),
            ])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_routines_are_drafted_for_residents_around_a_character_without_one(world):
    """名指しした人物と、`around_character_id` のエリアに住む人物のうち、決まった居場所の行の無い人物に、人物ごとに AI が
    決めた行を足す(出自は ai)。時間帯(朝・昼・夜)を暦の時に割り直し、続く時間帯で場所としていることが同じなら一行にまとめる。
    行ける場所の外の行・同じ時間帯の二つ目の行は外し、もう行のある人物は外してわけを返す。"""
    home_id, market_id = _detail_places(world)
    actor_id, resident_id = world.character_ids
    with get_env_session() as s:
        s.add(CharacterRoutine(character_id=actor_id, location_id=market_id, hour_from=8, hour_to=12, text="買い出し"))
        s.commit()
    ai = RoutineAI(market_id)

    with mock.patch("ai.claude_code.ai_client.generate", ai.generate):
        result = DraftRoutines(character_ids=[actor_id], around_character_id=actor_id, time=f"{_DAY} 12:00:00").run()

    assert [row["character_id"] for row in result["drafted"]] == [resident_id]
    assert [row["character_id"] for row in result["skipped"]] == [actor_id]
    prompt = json.loads(ai.calls[0]["prompt"].rsplit("\n", 1)[0])
    assert prompt["住まい"]["場所id"] == home_id
    assert {place["場所id"] for place in prompt["行ける場所"]} >= {home_id, market_id}
    with get_env_session() as s:
        rows = s.scalars(select(CharacterRoutine).where(CharacterRoutine.character_id == resident_id)).all()
        assert [(row.location_id, row.hour_from, row.hour_to, row.text, row.origin) for row in rows] == [
            (market_id, 6, 18, "野菜の屋台を開けている", "ai")]


def test_routine_periods_are_counted_in_the_calendar_and_the_night_crosses_midnight():
    """一日の長さが違う暦では、時間帯を暦の時に割り直す(半端は切り上げ)。夜は日付が変わるまでで、終わりは 0 時。"""
    character = RoutineCharacter(character_id=1, text="", histories=[], relations=[], home=DayPlace(id=1),
                                 places=[DayPlace(id=1), DayPlace(id=2)], hours_per_day=30)
    draft = RoutineDraft(routines=[RoutineDraftRow(period="朝", location_id=2, text="店番"),
                                   RoutineDraftRow(period="夜", location_id=2, text="酒場の手伝い")])

    rows = usable_rows(draft, character)

    assert [(row.hour_from, row.hour_to, row.text) for row in rows] == [(8, 15, "店番"), (23, 0, "酒場の手伝い")]


def test_the_center_of_routines_is_drafted_only_when_named(world):
    """`around_character_id` の人物は、ふつう動かす側なので、名指ししなければ決まった居場所を決めない。"""
    _, market_id = _detail_places(world)
    actor_id, resident_id = world.character_ids

    with mock.patch("ai.claude_code.ai_client.generate", RoutineAI(market_id).generate):
        result = DraftRoutines(around_character_id=actor_id, time=f"{_DAY} 12:00:00").run()

    assert [row["character_id"] for row in result["drafted"]] == [resident_id]
    assert result["skipped"] == []


def test_a_day_record_keeps_only_the_actor_busy(world):
    """人物モードの一日の出来事は、動いた人物だけを出来事の最中としてふさぐ。居合わせただけの動かしていない人物は、同じ日に
    後から動かす人物の目にも、決まった居場所にいるまま映る。"""
    _, market_id = _detail_places(world)
    actor_id, resident_id = world.character_ids
    with get_env_session() as s:
        s.add(CharacterRoutine(character_id=resident_id, location_id=market_id, hour_from=10, hour_to=20,
                               text="野菜の屋台を開けている", start="1199/01/01"))
        s.commit()

    run = act.simulate_day([actor_id], _DAY, seed=1, ai=ScriptedAI(market_id))

    assert not run.failed, run.failed
    assert resident_id in run.acted[0].event.character_ids
    noon = _stamp(f"{_DAY} 15:00:00")
    with get_env_session() as s:
        busy = set(s.scalars(world_creation_query.busy_character_ids_select(noon)).all())
    assert actor_id in busy and resident_id not in busy
    # 市場に来た人物の目には、動かしていない人物が屋台を開けているまま映る
    with get_env_session() as s:
        places = acting.people_at(s, PeopleForm(time=noon, positions={actor_id: market_id}))
    assert any(person.character_id == resident_id and person.routine == "野菜の屋台を開けている"
               for place in places for person in place.people)


def test_a_decided_action_lasts_by_its_kind_and_ends_early_when_hungry(world):
    """会話に聞いて決めた手は、決めた時間だけ聞かずに続く(起きて最初の手は一時間、三時間と決めた働くは三時間、食べるは一時間)。
    続けているあいだにおなかがすいたら、途中で終えて聞き直す。"""
    _, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    ai = ScriptedAI(market_id)

    act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    asked = [_clock_of(call["prompt"]) for call in ai.calls_of(HourDraft)]
    actions = {action.time.digits[3]: action for action in _actions(actor_id)}
    # 7 時に起きて最初の手は一時間。8 時に決めた「働く」は三時間続く(空腹で途中で終えなければ)
    assert asked[:2] == [7, 8]
    for start, end in zip(asked, asked[1:]):
        assert end - start <= 3
        if actions[start].kind == "食べる":
            assert end - start == 1
    assert len(asked) < 17


class LongWorkAI(ScriptedAI):
    """市場で、決める長さを `hours` にして働く(二時間目からは荷を運び続ける)。おなかがすいたら食べる。"""

    def __init__(self, market_id: int, hours: int):
        super().__init__(market_id)
        self.hours = hours

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        if output is HourDraft and not _reaction(prompt) and "おなかがすいた" not in prompt:
            self.calls.append({"output": output, "prompt": prompt})
            return HourDraft(hours=self.hours, after_action="荷を運び続ける", kind="働く", next_location_id=self.market_id,
                             action="市場の親方に今日の割り振りを頼んで、荷を運ぶ", toward_ids=_present_ids(prompt),
                             thought="", ate="なし", deeds=[])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)


def test_a_decided_action_lasts_as_long_as_drafted(world):
    """会話に聞いて決めた手は、決めた時間だけ聞かずに続き、二時間目からは `after_action` のことをしている
    (人への働きかけは最初の一時間だけ)。"""
    _, market_id = _detail_places(world)
    actor_id = world.character_ids[1]
    ai = LongWorkAI(market_id, 5)

    act.simulate_day([actor_id], _DAY, seed=1, ai=ai)

    asked = [_clock_of(call["prompt"]) for call in ai.calls_of(HourDraft)]
    actions = {action.time.digits[3]: action for action in _actions(actor_id)}
    work = [(begin, finish) for begin, finish in zip(asked, asked[1:]) if actions[begin].kind == "働く"]
    # 空腹・眠りで途中で終える手もあるが、いちばん長い手は決めた長さ(上限まで)続く
    assert max(finish - begin for begin, finish in work) == 5
    for begin, finish in work:
        assert actions[begin].text == "市場の親方に今日の割り振りを頼んで、荷を運ぶ"
        assert all(actions[hour].text == "荷を運び続ける" for hour in range(begin + 1, finish))


@pytest.mark.parametrize("kind, hours, deeds, woke, expected", [
    ("働く", 99, [], False, constants.DAY_BLOCK_MAX_HOURS),
    ("働く", 0, [], False, 1),
    ("食べる", 4, [], False, 1),
    ("働く", 4, [], True, 1),
    ("働く", 4, ["戦った"], False, 1),
])
def test_the_length_of_a_decided_action_is_capped(kind, hours, deeds, woke, expected):
    """決めた長さは、種別ごとの上限(食べる・触れ合う・移動は一時間、ほかは `DAY_BLOCK_MAX_HOURS`)で切り、1 より短くしない。
    起きて最初の手と、重い行いをした手は一時間。"""
    walker = SimpleNamespace(sleeping=[True] if woke else [False], block=None, block_until=0)
    choice = act._Choice(location_id=1, kind=kind, text="", deeds=deeds, hours=hours)

    act._start_block(walker, choice, 10)  # type: ignore[arg-type]

    assert walker.block_until - 10 == expected


def test_known_people_are_recalled_when_they_first_come_in_sight(world):
    """初めの材料には、知っている人物の外見・芯・来歴と、言ったセリフを載せない(関係の名前と間柄だけ)。名前を知っている人物が
    目の前に初めて来たときに、その人物について知っていることを一度だけ渡す。"""
    _, market_id = _detail_places(world)
    first_id, second_id = sorted(world.character_ids)
    with get_env_session() as s:
        second = s.get_one(Character, second_id)
        second_name, second_text = second.name, second.text
    ai = ScriptedAI(market_id)

    act.simulate_day(world.character_ids, _DAY, seed=1, ai=ai)

    asks = [call["prompt"] for call in ai.calls_of(HourDraft) if f"あなた({second_name})" not in call["prompt"]]
    first = json.loads(asks[0].rsplit("\n", 1)[0])
    assert first["あなたが知っていること"]["知っている人物"] == []
    assert "言ったセリフ(古い順)" not in first["あなたが知っていること"]["自分"]
    recalled = [prompt for prompt in asks if "目の前の知っている人物について、覚えていること" in prompt]
    assert len(recalled) == 1 and str(second_text) in recalled[0]
