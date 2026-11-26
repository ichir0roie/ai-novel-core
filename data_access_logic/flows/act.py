#!/usr/bin/env python3
"""人物モードの流れ(`SimulateDay`)。渡した人物たちの一日を、0 時から暦の一時間ずつ動かし、行動の表(`event_action`)に残して、
一日の終わりに人物ごとの一日を出来事一件にまとめる。

- 人物一人に会話(エージェント)を一つ持たせ、その人物の一日を一つの会話で回す。一度目の問いに一日のあいだ変わらない材料を渡し、
  二度目からはその一時間の様子の差分だけを渡す(`expansion/actor.py`)。一時間の始めにいる場所ごとの組の中は動く順(影響力・行動量)に
  一人ずつ、組どうしは並べて(並列に)回す。人物の目には、台詞でなく行いの粒で決めさせる
- 作者の出来事・話の予定がある時間は予定で埋め、眠っている時間(起きる・寝る時刻は計算で決める)と、疲れて休む時間は規則で埋めて、
  人物の会話には聞かない(`expansion/needs.py`)。聞かずに過ぎた時間は、次に聞くときに「過ぎた時間にしていたこと」として渡す
- 組の中の後の人物は、先の人物がこの一時間にしたことを見てから決める。先の人物は、後の人物に働きかけられたか、一緒にいた後の人物が
  場所を移るときだけ応じる(一往復)。次の一時間の材料には、目の前の人物がさっきしたことを渡す
- その日を先に動かした人物は、行動の表のとおりの場所と行いで目の前に出し、後から動く人物に合わせては変えない
- 動けるのは、人物のいるエリア(詳細の場所の一番近い、詳細でない上の場所)の詳細の場所のあいだだけ。詳細の場所にいない人物は動かさない
- 一日の終わりに、欲の満ち足り方と行動量を人物の一日の記録(`character_day`)に足す。次の日の欲の強さ・眠り・休みがちさと、
  欲を満たしたいモチベーションは、この記録から決まる
- 人物ごとに展開(`expansion`、mode=character)を一つ立て、書き手 `ai_append` で書くので、その一日の行動・記録・出来事・来歴などは
  `RevertExpansion` で人物の一日ごとに取り消せる

db の段は `data_access_logic/expansion/steps.py`、AI の段は `data_access_logic/expansion/actor.py`。
"""
from __future__ import annotations

import contextvars
import logging
import random
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ai.claude_code import ai_client
from data_access_logic import constants
from data_access_logic.ai_client import AIClient, AISession
from data_access_logic.caller import call
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.event_seed import steps as seed_steps
from data_access_logic.event_seed.extractor import draw_from
from data_access_logic.expansion import acting, actor, budget, needs
from data_access_logic.expansion import steps as expansion_steps
from data_access_logic.expansion.act_models import (
    ActFailure, ActionsForm, CharacterDayForm, DayActed, DayBrief, DayBriefForm, DayCharacter, DayForm,
    DayMaterialForm, DayPlace, DayPlan, DayRequest, DayRun, DaySaveForm, HourAction, HourScene, KnownPeopleForm,
    MotivesForm,
    NeedMotivationForm, Needs, NewCharacterLink, PeopleForm, PlacePeople,
)
from data_access_logic.expansion.form import ExpansionCreateForm, ExpansionFinishForm
from data_access_logic.flows import character as character_flow
from data_access_logic.flows.summary import refresh
from data_access_logic.story import steps as story_steps
from data_access_logic.story.steps import ScopeForm
from db import story_scope
from db.schema import ExpansionMode
from db.stamp import Stamp
from db.story_scope import Scope
from db.writer import Writer, writing

logger = logging.getLogger(__name__)

# 展開に残す、居合わせた相手とのやり取りの見出し。見取り図(`gui/api/overview.py`)がこの見出しから後を相手の行として読む
MET_HEAD = "居合わせた相手とのやり取り:"
_SLEEP = "眠る"
_FIXED = "予定"
_REST = "休む"


def _parallel[In, Out](work: Callable[[In], Out], items: Sequence[In]) -> list[Out]:
    """人物ごとの手を並べて回す。流れの文脈(db の段の口・作品と暦・書き手)を、手ごとに写して渡す。"""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        futures = [pool.submit(contextvars.copy_context().run, work, item) for item in items]
        return [future.result() for future in futures]


def _clock(hour: Stamp) -> str:
    return f"{hour.digits[3]}時"


@dataclass
class _Entry:
    """人物の一日の一行(続けて眠った・休んだ時間と、続けた手は一行にまとめる)。"""

    start: str
    end: str
    place: str
    kind: str
    text: str
    # 作者の目に渡す、居合わせた人物がその一時間にしたこと
    others: list[str] = field(default_factory=list)
    # 前の一時間に決めた手を続けた一時間か
    continuing: bool = False

    def for_character(self) -> str:
        span = self.start if self.start == self.end else f"{self.start}〜{self.end}"
        return f"{span}: {self.place}で、{self.text}"

    def for_author(self) -> str:
        return "\n".join([self.for_character(), *(f"  - {line}" for line in self.others)])


def _merged(entries: list[_Entry], entry: _Entry) -> None:
    if not entries:
        entries.append(entry)
        return
    last = entries[-1]
    same = last.kind == entry.kind and last.place == entry.place and last.text == entry.text
    if same and entry.continuing:
        last.end = entry.end
        last.others += [line for line in entry.others if line not in last.others]
        return
    if same and entry.kind in (_SLEEP, _REST) and not entry.others and not last.others:
        last.end = entry.end
        return
    entries.append(entry)


@dataclass
class _Walker:
    """一日を動いている人物の、流れの中の様子。"""

    plan: DayCharacter
    brief: DayBrief
    session: AISession
    places: list[DayPlace]
    # いまいる場所(前の一時間を過ごした場所)
    location_id: int
    needs: Needs
    rng: random.Random
    # 前の一時間に決めた、次の一時間を過ごす場所(決めていなければ None で、いまいる場所に残る)
    next_location_id: int | None = None
    # 会話に聞いて決めた手と、それを続ける時間の終わり(この番号の一時間からは続けない)
    block: _Choice | None = None
    block_until: int = 0
    entries: list[_Entry] = field(default_factory=list)
    # 前に聞いてから、会話に聞かずに過ぎた時間(次に聞くときに渡す)
    unseen: list[_Entry] = field(default_factory=list)
    asked: bool = False
    # 会話の中で見た目を渡した人物
    looked_ids: set[int] = field(default_factory=set)
    # 会話の中で、知っていること(外見・芯・来歴)を渡した、名前を知っている人物
    recalled_ids: set[int] = field(default_factory=set)
    # その夜、自分から床に就いたか(朝まで会話に聞かずに眠る)
    bedded: bool = False
    # 目の前の人物が、さっきの一時間にしたこと(見る人の目で)
    seen: list[str] = field(default_factory=list)
    # 居合わせた人物(人物id と名前)。起きているあいだに同じ場所にいた人物
    met: dict[int, str | None] = field(default_factory=dict)
    # 居合わせた人物ごとの、居合わせた場所の名前
    met_places: dict[int, list[str]] = field(default_factory=dict)
    # 居合わせて互いに応じた、動かしている相手
    met_walkers: dict[int, str] = field(default_factory=dict)
    awake_places: Counter[int] = field(default_factory=Counter)
    first_awake: Stamp | None = None
    hungers: list[int] = field(default_factory=list)
    desires: list[int] = field(default_factory=list)
    # 一時間ごとに眠っていたか(起きた順)
    sleeping: list[bool] = field(default_factory=list)
    load: int = 0
    actions: int = 0
    failed: str | None = None

    @property
    def id(self) -> int:
        return self.plan.character_id

    @property
    def name(self) -> str:
        return self.plan.name or ""

    def append(self, entry: _Entry, asked: bool) -> None:
        _merged(self.entries, entry)
        if not asked:
            _merged(self.unseen, entry)


@dataclass
class _Choice:
    """一時間の手。人物の会話に聞いた手か、予定・規則で埋めた手。"""

    # この一時間を過ごす場所(一時間の始めに、全員が先に移ってある)
    location_id: int
    kind: str
    text: str
    thought: str | None = None
    deeds: list[str] = field(default_factory=list)
    # この一時間に働きかけた目の前の人物
    toward_ids: list[int] = field(default_factory=list)
    asked: bool = False
    fixed_event_id: int | None = None
    fixed_episode_id: int | None = None
    # この一時間に食べた量(`DAY_MEAL_AMOUNTS`)
    ate: str = constants.DAY_MEAL_AMOUNTS[0]
    # 次の一時間を過ごす場所(None ならこの一時間の場所に残る)
    next_location_id: int | None = None
    # 前の一時間に決めた手を、会話に聞かずに続けた一時間か
    continuing: bool = False


def _seen_name(viewer: _Walker, character_id: int, name: str | None) -> str:
    return name if character_id in viewer.brief.known_ids and name else "名を知らない人"


def _schedule(walker: _Walker, plan: DayPlan) -> list[str]:
    """一度目の問いに渡す、今日決まっている予定(予定ごとに始まりの時刻)と、眠る時刻の目安。"""
    lines: list[str] = []
    last_label = None
    for slot in walker.plan.fixed:
        if slot.label != last_label:
            lines.append(f"{_clock(plan.hours[slot.hour])}から: {slot.label}")
        last_label = slot.label
    bed = walker.plan.profile.bed
    hours = len(plan.hours)
    if bed < hours:
        lines.append(f"{_clock(plan.hours[bed])}ごろ: 眠る")
    else:
        lines.append("日付が変わるころ: 眠る" if bed == hours else f"日付が変わって{bed - hours}時ごろ: 眠る")
    return lines


def _scene(walker: _Walker, index: int, plan: DayPlan, location_id: int, here: PlacePeople | None,
           now: list[str]) -> HourScene:
    return HourScene(
        time=plan.hours[index], location_id=location_id,
        location_name=None if here is None else here.location_name, needs=walker.needs,
        fatigue=needs.fatigue(walker.plan.profile, walker.load),
        meanwhile=[entry.for_character() for entry in walker.unseen],
        present=[] if here is None else [person for person in here.people if person.character_id != walker.id],
        seen=walker.seen, now=now, until_bed=walker.plan.profile.bed - index)


def _near_bed(walker: _Walker, index: int, plan: DayPlan) -> bool:
    return index >= walker.plan.profile.bed - round(constants.DAY_EARLY_BED_HOURS * len(plan.hours) / 24)


def _planned(walker: _Walker) -> int:
    """前の一時間に決めた、この一時間を過ごす場所。"""
    return walker.next_location_id or walker.location_id


def _ruled(walker: _Walker, index: int, plan: DayPlan) -> _Choice | None:
    """会話に聞かずに決まる一時間(予定・眠る・決めた手の続き・疲れて休む)と、その場所。どれでもなければ None(会話に聞く)。
    予定・眠り・空腹(食べる手でないとき)は、決めた手を途中で終える。"""
    block, walker.block = walker.block, None
    slot = walker.plan.fixed_at(index)
    if slot is not None:
        went_out = slot.location_id != walker.plan.home_id
        return _Choice(location_id=slot.location_id, kind=_FIXED, text=slot.label, deeds=["外に出た"] if went_out else [],
                       fixed_event_id=slot.event_id, fixed_episode_id=slot.episode_id)
    profile = walker.plan.profile
    if walker.bedded or needs.asleep_at(index, profile):
        # 夜に眠るときは寝床(その日の始まりの場所)へ戻る
        location_id = walker.location_id if index < profile.wake else walker.plan.home_id
        return _Choice(location_id=location_id, kind=_SLEEP, text="眠っていた")
    hungry = walker.needs.hunger >= constants.DAY_NEED_COMFORT
    if block is not None and index < walker.block_until and not (hungry and block.kind != "食べる"):
        walker.block = block
        return _Choice(location_id=block.location_id, kind=block.kind, text=block.text, deeds=block.deeds,
                       next_location_id=block.next_location_id, continuing=True)
    if not hungry and walker.rng.random() < needs.rest_chance(needs.fatigue(profile, walker.load)):
        if _near_bed(walker, index, plan):
            # 疲れて寝る時刻が近ければ、そのまま床に就く
            walker.bedded = True
            return _Choice(location_id=walker.plan.home_id, kind=_SLEEP, text="疲れがたまっていて、早めに床に就いた")
        return _Choice(location_id=_planned(walker), kind=_REST, text="疲れがたまっていて、その場で休んだ")
    return None


def _recalled(walker: _Walker, scene: HourScene) -> dict | None:
    """目の前に初めて来た、名前を知っている人物について、本人が知っていること(外見・芯・来歴)。初めの材料には載せず、
    来たときにだけ渡す。"""
    new_ids = [person.character_id for person in scene.present
               if person.character_id in walker.brief.known_ids and person.character_id not in walker.recalled_ids]
    if not new_ids:
        return None
    walker.recalled_ids.update(new_ids)
    return call(expansion_steps.known_people, KnownPeopleForm(viewer_id=walker.id, character_ids=new_ids,
                                                              time=scene.time)).prompt


def _ask(walker: _Walker, index: int, plan: DayPlan, location_id: int, here: PlacePeople | None,
         now: list[str]) -> _Choice:
    """人物の会話に、いまいる場所でのこの一時間と、次の一時間を過ごす場所を聞く。`now` は同じ場所で先に動いた人物が、この一時間に
    していること(見る人の目で)。"""
    scene = _scene(walker, index, plan, location_id, here, now)
    first = None if walker.asked else walker.places
    draft = actor.hour_draft(walker.session, walker.brief, scene, walker.looked_ids, first,
                             _schedule(walker, plan) if first else None, _recalled(walker, scene))
    walker.asked = True
    walker.unseen = []
    if draft is None:
        return _Choice(location_id=location_id, kind=_REST, text="その場でしばらく過ごした")
    place_ids = {place.id for place in walker.places}
    next_location_id = draft.next_location_id if draft.next_location_id in place_ids else location_id
    night = index >= round(constants.DAY_NIGHT_START * len(plan.hours) / 24)
    if draft.kind == _SLEEP and (_near_bed(walker, index, plan) or night):
        walker.bedded = True
        next_location_id = walker.plan.home_id
    present_ids = {person.character_id for person in scene.present}
    choice = _Choice(location_id=location_id, kind=draft.kind, text=draft.action, thought=draft.thought, deeds=draft.deeds,
                     toward_ids=[id_ for id_ in dict.fromkeys(draft.toward_ids) if id_ in present_ids], asked=True,
                     ate=draft.ate, next_location_id=next_location_id)
    if not walker.bedded:
        _start_block(walker, choice, index)
    return choice


def _start_block(walker: _Walker, choice: _Choice, index: int) -> None:
    """決めた手を、種別ごとの時間だけ続ける。起きて最初の手と、重い行いをした手は一時間で区切る。"""
    woke = not walker.sleeping or walker.sleeping[-1]
    short = woke or any(deed in constants.DAY_SHORT_DEEDS for deed in choice.deeds)
    hours = 1 if short else constants.DAY_KIND_HOURS.get(choice.kind, constants.DAY_BLOCK_HOURS)
    walker.block, walker.block_until = choice, index + hours


def _leaving(choice: _Choice) -> bool:
    return choice.next_location_id is not None and choice.next_location_id != choice.location_id


def _seen_deed(viewer: _Walker, other: _Walker, other_choice: _Choice) -> str:
    """見る人の目で、相手がこの一時間にしたこと。次の一時間に別の場所へ移るなら、移る先を添える。"""
    if other_choice.kind == _SLEEP:
        return f"{_seen_name(viewer, other.id, other.name)}: 眠っている"
    names = {place.id: place.name for place in viewer.places}
    moving = (f"({names.get(other_choice.next_location_id or 0) or 'ほかの場所'}へ移るところ)"
              if _leaving(other_choice) else "")
    return f"{_seen_name(viewer, other.id, other.name)}: {other_choice.text}{moving}"


def _react(walker: _Walker, choice: _Choice, others: list[tuple[_Walker, _Choice]]) -> _Choice:
    """同じ場所で後に動いた人物がこの一時間にしたことを見せて、応じさせる。応じた分を一時間の手に書き足し、応じて次の一時間の
    場所が変わったら(移る相手についていくなど)、それも差し替える。"""
    draft = actor.reaction_draft(walker.session, walker.brief, [_seen_deed(walker, other, other_choice)
                                                                for other, other_choice in others])
    if draft is None:
        return choice
    thoughts = [thought for thought in (choice.thought, draft.thought) if thought]
    place_ids = {place.id for place in walker.places}
    next_location_id = draft.next_location_id if draft.next_location_id in place_ids else choice.next_location_id
    # 応じて過ごし方が変わったら(誘われて一緒に食べたなど)、欲の動きもそちらで数える
    return _Choice(location_id=choice.location_id, kind=draft.kind, text=f"{choice.text}\n{draft.action}",
                   thought="\n".join(thoughts) or None, deeds=list(dict.fromkeys([*choice.deeds, *draft.deeds])),
                   toward_ids=choice.toward_ids, asked=True,
                   ate=max(choice.ate, draft.ate, key=constants.DAY_MEAL_AMOUNTS.index), next_location_id=next_location_id)


def _people(walkers: list[_Walker], time: Stamp, positions: list[int]) -> dict[int, PlacePeople]:
    return {place.location_id: place for place in call(expansion_steps.people_at, PeopleForm(
        time=time, positions={walker.id: location_id for walker, location_id in zip(walkers, positions)}))}


def _hour(walkers: list[_Walker], index: int, plan: DayPlan) -> None:
    """一時間を二段で回す。動く段で、全員を、予定・眠りの規則か前の一時間に決めた場所へ先に移す。する段で、場所ごとの組の中は
    動く順に一人ずつ、そこにいる人物(動かしている人物・先に動かした人物・決まった居場所にいる動かしていない人物)を見て行いと
    次の一時間の場所を決め(後の人物は先の人物のしたことを見る)、組どうしは並べて回す。先の人物のうち、後の人物に働きかけられたか、
    一緒にいた後の人物が別の場所へ移るのを見た人物を応じさせ、行動の表に足す。"""
    hour = plan.hours[index]
    hours_per_day = len(plan.hours)
    ruled = {walker.id: _ruled(walker, index, plan) for walker in walkers}
    positions = {walker.id: (choice.location_id if (choice := ruled[walker.id]) else _planned(walker))
                 for walker in walkers}
    present = _people(walkers, hour, [positions[walker.id] for walker in walkers])
    groups: dict[int, list[_Walker]] = {}
    for walker in sorted(walkers, key=lambda walker: acting.move_order(walker.plan)):
        groups.setdefault(positions[walker.id], []).append(walker)

    def decide(group: list[_Walker]) -> list[tuple[_Walker, _Choice]]:
        decided: list[tuple[_Walker, _Choice]] = []
        for walker in group:
            choice = ruled[walker.id]
            if choice is None:
                location_id = positions[walker.id]
                now = [_seen_deed(walker, other, other_choice) for other, other_choice in decided]
                choice = _ask(walker, index, plan, location_id, present.get(location_id), now)
            decided.append((walker, choice))
        return decided

    decided = {walker.id: choice for pairs in _parallel(decide, list(groups.values())) for walker, choice in pairs}

    def react(walker: _Walker) -> _Choice:
        choice = decided[walker.id]
        if not (choice.asked or choice.continuing) or choice.kind == _SLEEP:
            return choice
        group = groups[positions[walker.id]]
        # 後の人物は先の人物の手を見てから決めているので、応じるのは先の人物だけ。働きかけられたか、一緒にいた人物が別の場所へ移るとき
        # (前に決めた手を続けている人物は、働きかけられたときだけ)
        others = [(other, decided[other.id]) for other in group[group.index(walker) + 1:]
                  if decided[other.id].kind != _SLEEP
                  and (walker.id in decided[other.id].toward_ids
                       or (choice.asked and _leaving(decided[other.id])
                           and decided[other.id].next_location_id != (choice.next_location_id or choice.location_id)))]
        if not others:
            return choice
        reacted = _react(walker, choice, others)
        # 続けていた手は応じたところで終え、次の一時間に決め直す。決めたばかりの手は、応じた形で続ける
        walker.block = None if choice.continuing else reacted
        return reacted

    reacted = dict(zip([walker.id for walker in walkers], _parallel(react, walkers)))
    for walker in walkers:
        choice = reacted[walker.id]
        here = present.get(choice.location_id)
        awake = choice.kind != _SLEEP
        companions = [] if here is None else [person for person in here.people if person.character_id != walker.id]
        others = [(other, reacted[other.id]) for other in groups[choice.location_id] if other.id != walker.id]
        # その日を先に動かした人物の、行動の表のこの一時間
        recorded = [person for person in companions if person.doing is not None]
        if awake:
            walker.awake_places[choice.location_id] += 1
            walker.first_awake = walker.first_awake or hour
            walker.met.update({person.character_id: person.name for person in companions})
            for person in companions:
                places = walker.met_places.setdefault(person.character_id, [])
                if here is not None and here.location_name and here.location_name not in places:
                    places.append(here.location_name)
            walker.met_walkers.update({other.id: other.name for other, other_choice in others
                                       if other_choice.kind != _SLEEP})
        walker.sleeping.append(not awake)
        walker.seen = [_seen_deed(walker, other, other_choice) for other, other_choice in others]
        walker.seen += [f"{_seen_name(walker, person.character_id, person.name)}: {person.doing}" for person in recorded]
        load = needs.hour_load(choice.deeds)
        walker.load += load
        walker.location_id = choice.location_id
        walker.next_location_id = choice.next_location_id
        walker.needs = needs.next_needs(walker.needs, choice.kind, index, hours_per_day, walker.plan.profile, choice.ate)
        walker.hungers.append(walker.needs.hunger)
        walker.desires.append(walker.needs.desire)
        walker.append(_Entry(
            start=_clock(hour), end=_clock(hour), place=(here.location_name if here else None) or "",
            kind=choice.kind, text=choice.text, continuing=choice.continuing,
            others=[*(f"{other.name}: " + ("眠っている" if other_choice.kind == _SLEEP else other_choice.text)
                      for other, other_choice in others),
                    *(f"{person.name}(先に決まった一日): {person.doing}" for person in recorded),
                    *(f"{person.name}(動かしていない人物)" + (f": {person.routine}" if person.routine else "")
                      for person in companions if not person.simulated and person.doing is None)]),
            choice.asked or choice.continuing)
        action = HourAction(
            character_id=walker.id, time=hour, location_id=choice.location_id, kind=choice.kind, text=choice.text,
            thought=choice.thought, sleepiness=walker.needs.sleepiness, hunger=walker.needs.hunger,
            desire=walker.needs.desire, load=load, fixed_event_id=choice.fixed_event_id,
            fixed_episode_id=choice.fixed_episode_id)
        assert walker.plan.expansion_id is not None
        with writing(Writer.AI_APPEND, walker.plan.expansion_id):
            call(expansion_steps.save_actions, ActionsForm(expansion_id=walker.plan.expansion_id, actions=[action]))
        walker.actions += 1


def _prompt_text(walker: _Walker) -> str:
    """展開に残す人物の一日。居合わせて応じ合った相手は見出しの下に一人一行で(見取り図が相手として読む)。"""
    lines = [entry.for_character() for entry in walker.entries]
    if walker.met_walkers:
        lines += [MET_HEAD, *(f"- {name}: 同じ場所に居合わせて、互いに応じた" for name in walker.met_walkers.values())]
    return "\n".join(lines)


def _summary(acted: DayActed, walker: _Walker, satisfied: tuple[int, int, int]) -> str:
    food, sleep, touch = satisfied
    lines = [f"{acted.name}(id={acted.character_id}) の一日: 行動 {acted.actions} 件・行動量 {walker.load}",
             f"満ち足り方: 食欲 {food}・睡眠欲 {sleep}・性欲 {touch}",
             f"出来事: {acted.event.name}(id={acted.event.id})"]
    if walker.met_walkers:
        lines.append(f"居合わせた相手: {', '.join(walker.met_walkers.values())}")
    if acted.idea_ids:
        lines.append(f"事柄: アイデア id={', '.join(map(str, acted.idea_ids))}")
    if acted.characters:
        lines.append(f"現れた人物: {', '.join(f'{c.name}(id={c.id})' for c in acted.characters)}")
    if acted.moves:
        lines.append(f"居場所の移動: {len(acted.moves)} 人")
    if acted.motivations:
        lines.append("モチベーション: " + "; ".join(
            f"人物 id={row.character_id} {row.text}(強さ {row.strength})" for row in acted.motivations))
    if acted.frame is not None:
        lines.append(f"影響力: {acted.frame.influence}")
    return "\n".join(lines)


def _satisfied(walker: _Walker) -> tuple[int, int, int]:
    return needs.satisfaction(walker.hungers, walker.desires, needs.last_night(walker.sleeping, walker.plan.profile),
                              walker.plan.profile)


def _record(ai: AIClient, rng: random.Random, walker: _Walker, plan: DayPlan, walker_ids: set[int]) -> DayActed:
    """人物の一日の欲の満ち足り方と行動量を記録し、一日を作者の目で記録して、出来事一件と、来歴・事柄・住まいの移動・思いの増減として足す。"""
    expansion_id = walker.plan.expansion_id
    assert expansion_id is not None
    date = Stamp.parse(plan.date)
    day_end = Stamp.parse(plan.day_end)
    assert date is not None and day_end is not None
    food, sleep, touch = _satisfied(walker)
    with writing(Writer.AI_APPEND, expansion_id):
        call(expansion_steps.save_character_day, CharacterDayForm(
            character_id=walker.id, expansion_id=expansion_id, date=date, food=food, sleep=sleep, touch=touch,
            load=walker.load, bedtime=needs.bedtime(walker.sleeping, walker.plan.profile)))
    material = call(expansion_steps.day_material, DayMaterialForm(
        actor_id=walker.id, participant_ids=list(walker.met), date=date, day_end=day_end,
        home_id=walker.plan.home_id, parent_event_id=plan.parent_event_id))
    request = DayRequest(actor_name=walker.name, log=[entry.for_author() for entry in walker.entries],
                         present={walker.id: walker.name, **walker.met}, met_places=walker.met_places,
                         material=material, date=date)
    outcome = actor.judge_draft(ai, request)
    if outcome is None:
        raise ValueError("一日の記録が得られなかった")
    # 一緒に動かした人物の人となりと思いは、その人物の一日の記録が書く(両方の記録が書くと、同じ思いがだぶる)
    others = walker_ids - {walker.id}
    outcome = outcome.model_copy(update={
        "character_updates": [row for row in outcome.character_updates if row.character_id not in others],
        "motivation_changes": [row for row in outcome.motivation_changes if row.character_id not in others]})
    outcome = budget.clamp(outcome, material.frame, walker.id)
    time = walker.first_awake or date
    location_id = walker.awake_places.most_common(1)[0][0] if walker.awake_places else walker.plan.home_id
    with writing(Writer.AI_APPEND, expansion_id):
        saved = call(expansion_steps.save_day, DaySaveForm(
            actor_id=walker.id, time=time, end=day_end, location_id=location_id, participant_ids=list(walker.met),
            destinations=material.destinations, outcome=outcome, parent_event_id=plan.parent_event_id))
        created = []
        for draft in outcome.new_characters:
            record = character_flow.generate(ai, rng, saved.newcomer_location_id, time, draft.person,
                                             CharacterForm(text=draft.description))
            if record is None:
                logger.warning(f"現れる人物「{draft.description[:30]}」を作れなかった")
                continue
            call(expansion_steps.link_new_character, NewCharacterLink(
                actor_id=walker.id, character_id=record.id, event_id=saved.event.id,
                relation=draft.relation or "知り合い", time=time))
            created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=saved.newcomer_location_id))
    return DayActed(expansion_id=expansion_id, character_id=walker.id, name=walker.name, event=saved.event,
                    actions=walker.actions, idea_ids=saved.idea_ids, characters=created, moves=saved.moves,
                    motivations=saved.motivations, met_ids=list(walker.met_walkers), frame=material.frame)


def _fail(run: DayRun, walker: _Walker, error: Exception) -> None:
    logger.exception(f"{walker.name}(id={walker.id})の一日を動かせなかった")
    walker.failed = str(error)
    if walker.plan.expansion_id is not None:
        call(expansion_steps.note_prompt, expansion_steps.PromptForm(
            expansion_id=walker.plan.expansion_id, prompt=_prompt_text(walker)))
        call(expansion_steps.finish_expansion, ExpansionFinishForm(id=walker.plan.expansion_id, status="failed"))
    run.failed.append(ActFailure(expansion_id=walker.plan.expansion_id, character_id=walker.id, name=walker.name,
                                 error=str(error)))


def _walkers(ai: AIClient, rng: random.Random, plan: DayPlan, nudge: str | None) -> list[_Walker]:
    """人物ごとに一日の展開を立て、さかのぼった不足から欲を満たしたいモチベーションをそろえてから、一日のあいだ変わらない材料を読む。"""
    date = Stamp.parse(plan.date)
    assert date is not None
    refresh(ai, call(expansion_steps.motive_targets, MotivesForm(
        character_ids=[character.character_id for character in plan.characters], time=date)))
    pool = call(seed_steps.seed_pool)
    walkers = []
    for character in plan.characters:
        expansion = call(expansion_steps.start_expansion, ExpansionCreateForm(
            mode=ExpansionMode.CHARACTER, actor_id=character.character_id, time=date, location_id=character.home_id))
        character.expansion_id = expansion.id
        with writing(Writer.AI_APPEND, expansion.id):
            call(expansion_steps.need_motivations, NeedMotivationForm(
                character_id=character.character_id, time=date, strengths=character.need_strengths))
        brief = call(expansion_steps.day_brief, DayBriefForm(
            character_id=character.character_id, time=date, seeds=draw_from(rng, pool), nudge=nudge))
        walkers.append(_Walker(plan=character, brief=brief, session=actor.agent(ai),
                               places=plan.places[character.area_id], location_id=character.home_id,
                               needs=character.needs, rng=random.Random(rng.randrange(2**31))))
    return walkers


def _plan(character_ids: list[int] | None, date: Stamp | str | None,
          parent_event_id: int | None = None) -> tuple[DayPlan, Scope | None]:
    """一日の段取りと、動かす人物の暦(動かせる人物がいなければ None)。"""
    first_ids = list(character_ids or [])
    if first_ids:
        scope = call(story_steps.read_scope, ScopeForm(args={"character_id": first_ids[0]})).scope()
    else:
        scope = story_scope.current() or Scope()
    with story_scope.scoped(scope):
        plan = call(expansion_steps.plan_day, DayForm(
            character_ids=first_ids, date=Stamp.parse(date), parent_event_id=parent_event_id))
    if not plan.characters:
        return plan, None
    # 動かす人物の暦で、その日の一時間を数える(暦の違う人物は段取りで外してある)
    return plan, call(story_steps.read_scope, ScopeForm(args={"character_id": plan.characters[0].character_id})).scope()


def simulate_day(
    character_ids: list[int] | None = None, date: Stamp | str | None = None, nudge: str | None = None,
    seed: int | None = None, ai: AIClient = ai_client, parent_event_id: int | None = None,
) -> DayRun:
    """`SimulateDay` に当たる。動かせない人物は失敗として返し、ほかの人物の一日は動かす。一人の一時間が組めなくても、
    その人物を止めるだけで、ほかの人物は続ける(止めた人物の展開は failed で残り、足せた行は展開ごと取り消せる)。"""
    rng = random.Random(seed)
    run = DayRun()
    plan, scope = _plan(character_ids, date, parent_event_id)
    run.failed += plan.failed
    if scope is None:
        return run
    run.keep_scope(scope)
    with story_scope.scoped(scope):
        run.date = plan.date
        run.day_end = plan.day_end
        walkers = _walkers(ai, rng, plan, nudge)
        for index in range(len(plan.hours)):
            active = [walker for walker in walkers if walker.failed is None]
            if not active:
                break
            try:
                _hour(active, index, plan)
            except Exception as error:
                for walker in active:
                    _fail(run, walker, error)
        survivors = [walker for walker in walkers if walker.failed is None]
        # 乱数は並べる前に人物ごとに分けておく(並べた先で一つの乱数を取り合わない)
        seeds = {walker.id: rng.randrange(2**31) for walker in survivors}

        def record(walker: _Walker) -> DayActed | Exception:
            try:
                return _record(ai, random.Random(seeds[walker.id]), walker, plan, {other.id for other in walkers})
            except Exception as error:
                return error

        for walker, result in zip(survivors, _parallel(record, survivors)):
            if isinstance(result, Exception):
                _fail(run, walker, result)
                continue
            assert walker.plan.expansion_id is not None
            call(expansion_steps.note_prompt, expansion_steps.PromptForm(
                expansion_id=walker.plan.expansion_id, prompt=_prompt_text(walker)))
            call(expansion_steps.finish_expansion, ExpansionFinishForm(
                id=walker.plan.expansion_id, summary=_summary(result, walker, _satisfied(walker))))
            run.acted.append(result)
    return run
