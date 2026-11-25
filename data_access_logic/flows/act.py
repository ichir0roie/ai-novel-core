#!/usr/bin/env python3
"""人物モードの流れ(`SimulateDay`)。渡した人物たちの一日を、0 時から暦の一時間ずつ動かし、行動の表(`event_action`)に残して、
一日の終わりに人物ごとの一日を出来事一件にまとめる。

- 人物一人に会話(エージェント)を一つ持たせ、その人物の一日を一つの会話で回す。一度目の問いに一日のあいだ変わらない材料を渡し、
  二度目からはその一時間の様子の差分だけを渡す(`expansion/actor.py`)。人物どうしの一時間は並べて(並列に)回す
- 作者の出来事・話の予定がある時間は予定で埋め、眠っている時間(起きる・寝る時刻は計算で決める)と、疲れて休む時間は規則で埋めて、
  人物の会話には聞かない(`expansion/needs.py`)。聞かずに過ぎた時間は、次に聞くときに「過ぎた時間にしていたこと」として渡す
- 手を決めたら、同じ場所に居合わせた人物どうしに、相手がこの一時間にしたことを見せて応じさせる(一往復)。次の一時間の材料には、
  目の前の人物がさっきしたことを渡す
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
from data_access_logic.expansion import actor, budget, needs
from data_access_logic.expansion import steps as expansion_steps
from data_access_logic.expansion.act_models import (
    ActFailure, ActionsForm, CharacterDayForm, DayActed, DayBrief, DayBriefForm, DayCharacter, DayForm,
    DayMaterialForm, DayPlace, DayPlan, DayRequest, DayRun, DaySaveForm, HourAction, HourScene, MotivesForm,
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


def _quoted(speech: str | None) -> str:
    """言葉を一言ずつかぎかっこに入れる(自分で決めた手と応じた手の言葉は改行でつないであり、一つにくくると一続きの言葉に読まれる)。"""
    return "".join(f"「{line}」" for line in (speech or "").split("\n") if line.strip())


@dataclass
class _Entry:
    """人物の一日の一行(続けて眠った・休んだ時間は一行にまとめる)。"""

    start: str
    end: str
    place: str
    kind: str
    text: str
    speech: str | None = None
    # 作者の目に渡す、居合わせた人物がその一時間にしたこと
    others: list[str] = field(default_factory=list)

    def for_character(self) -> str:
        span = self.start if self.start == self.end else f"{self.start}〜{self.end}"
        return f"{span}: {self.place}で、{self.text}" + _quoted(self.speech)

    def for_author(self) -> str:
        return "\n".join([self.for_character(), *(f"  - {line}" for line in self.others)])


def _merged(entries: list[_Entry], entry: _Entry) -> None:
    last = entries[-1] if entries else None
    if (last is not None and entry.kind in (_SLEEP, _REST) and last.kind == entry.kind and last.place == entry.place
            and last.text == entry.text and not entry.others and not last.others):
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
    location_id: int
    needs: Needs
    rng: random.Random
    entries: list[_Entry] = field(default_factory=list)
    # 前に聞いてから、会話に聞かずに過ぎた時間(次に聞くときに渡す)
    unseen: list[_Entry] = field(default_factory=list)
    asked: bool = False
    # 会話の中で見た目を渡した人物
    looked_ids: set[int] = field(default_factory=set)
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

    location_id: int
    kind: str
    text: str
    speech: str | None = None
    thought: str | None = None
    deeds: list[str] = field(default_factory=list)
    asked: bool = False
    fixed_event_id: int | None = None
    fixed_episode_id: int | None = None
    # この一時間に食べた量(`DAY_MEAL_AMOUNTS`)
    ate: str = constants.DAY_MEAL_AMOUNTS[0]


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


def _scene(walker: _Walker, index: int, plan: DayPlan, here: PlacePeople | None) -> HourScene:
    return HourScene(
        time=plan.hours[index], location_id=walker.location_id,
        location_name=None if here is None else here.location_name, needs=walker.needs,
        fatigue=needs.fatigue(walker.plan.profile, walker.load),
        meanwhile=[entry.for_character() for entry in walker.unseen],
        present=[] if here is None else [person for person in here.people if person.character_id != walker.id],
        seen=walker.seen, until_bed=walker.plan.profile.bed - index)


def _choose(walker: _Walker, index: int, plan: DayPlan, here: PlacePeople | None) -> _Choice:
    """予定があれば予定、眠る時間なら眠る、疲れて休む見込みに当たれば休む。どれでもなければ人物の会話に聞く。"""
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
    near_bed = index >= profile.bed - round(constants.DAY_EARLY_BED_HOURS * len(plan.hours) / 24)
    if not hungry and walker.rng.random() < needs.rest_chance(needs.fatigue(profile, walker.load)):
        if near_bed:
            # 疲れて寝る時刻が近ければ、そのまま床に就く
            walker.bedded = True
            return _Choice(location_id=walker.plan.home_id, kind=_SLEEP, text="疲れがたまっていて、早めに床に就いた")
        return _Choice(location_id=walker.location_id, kind=_REST, text="疲れがたまっていて、その場で休んだ")
    scene = _scene(walker, index, plan, here)
    first = None if walker.asked else walker.places
    draft = actor.hour_draft(walker.session, walker.brief, scene, walker.looked_ids, first,
                             _schedule(walker, plan) if first else None)
    walker.asked = True
    walker.unseen = []
    if draft is None:
        return _Choice(location_id=walker.location_id, kind=_REST, text="その場でしばらく過ごした")
    place_ids = {place.id for place in walker.places}
    location_id = draft.location_id if draft.location_id in place_ids else walker.location_id
    night = index >= round(constants.DAY_NIGHT_START * len(plan.hours) / 24)
    if draft.kind == _SLEEP and (near_bed or night):
        walker.bedded = True
        location_id = walker.plan.home_id
    return _Choice(location_id=location_id, kind=draft.kind, text=draft.action, speech=draft.speech,
                   thought=draft.thought, deeds=draft.deeds, asked=True, ate=draft.ate)


def _deed(choice: _Choice) -> str:
    return choice.text + _quoted(choice.speech)


def _seen_deed(viewer: _Walker, other: _Walker, other_choice: _Choice, origin_id: int) -> str:
    """見る人の目で、相手がこの一時間にしたこと。一時間の始めの場所(`origin_id`)から移るなら、移る先を添える。"""
    if other_choice.kind == _SLEEP:
        return f"{_seen_name(viewer, other.id, other.name)}: 眠っている"
    names = {place.id: place.name for place in viewer.places}
    moving = (f"({names.get(other_choice.location_id) or 'ほかの場所'}へ移る)"
              if other_choice.location_id != origin_id else "")
    return f"{_seen_name(viewer, other.id, other.name)}: {_deed(other_choice)}{moving}"


def _react(walker: _Walker, choice: _Choice, others: list[tuple[_Walker, _Choice]]) -> _Choice:
    """居合わせた人物がこの一時間にしたことを見せて、応じさせる。応じた分を一時間の手に書き足し、応じて場所を移ったら
    (場所を移る相手についていくなど)、過ごす場所も差し替える。"""
    draft = actor.reaction_draft(walker.session, walker.brief, [_seen_deed(walker, other, other_choice, other.location_id)
                                                                for other, other_choice in others])
    if draft is None:
        return choice
    speeches = [speech for speech in (choice.speech, draft.speech) if speech]
    thoughts = [thought for thought in (choice.thought, draft.thought) if thought]
    place_ids = {place.id for place in walker.places}
    location_id = draft.location_id if draft.location_id in place_ids else choice.location_id
    # 応じて過ごし方が変わったら(誘われて一緒に食べたなど)、欲の動きもそちらで数える
    return _Choice(location_id=location_id, kind=draft.kind or choice.kind, text=f"{choice.text}\n{draft.action}",
                   speech="\n".join(speeches) or None, thought="\n".join(thoughts) or None,
                   deeds=list(dict.fromkeys([*choice.deeds, *draft.deeds])), asked=True,
                   ate=max(choice.ate, draft.ate, key=constants.DAY_MEAL_AMOUNTS.index))


def _people(walkers: list[_Walker], time: Stamp, positions: list[int]) -> dict[int, PlacePeople]:
    return {place.location_id: place for place in call(expansion_steps.people_at, PeopleForm(
        time=time, positions={walker.id: location_id for walker, location_id in zip(walkers, positions)}))}


def _hour(walkers: list[_Walker], index: int, plan: DayPlan, before: dict[int, PlacePeople]) -> dict[int, PlacePeople]:
    """全員の一時間を決めて、言葉を交わした人物・一緒にいて場所を移る人物と居合わせた人物を応じさせ、行動の表に足す。
    `before` は一時間の始まりに目の前にいる人物(前の一時間の終わりの居場所)。この一時間の終わりの居場所で読んだ、
    目の前にいる人物を返す。"""
    hour = plan.hours[index]
    hours_per_day = len(plan.hours)
    origins = {walker.id: walker.location_id for walker in walkers}
    choices = _parallel(lambda walker: _choose(walker, index, plan, before.get(walker.location_id)), walkers)
    decided = dict(zip([walker.id for walker in walkers], choices))

    def react(walker: _Walker) -> _Choice:
        choice = decided[walker.id]
        # 一時間の始めに同じ場所にいた人物と、同じ場所で過ごす人物(`location_id` はまだ一時間の始めの場所)
        others = [(other, decided[other.id]) for other in walkers if other.id != walker.id
                  and (other.location_id == walker.location_id or decided[other.id].location_id == choice.location_id)]
        awake = [(other, other_choice) for other, other_choice in others if other_choice.kind != _SLEEP]
        spoke = any(other_choice.speech for _, other_choice in awake)
        left = any(other.location_id == walker.location_id and other_choice.location_id != other.location_id
                   and other_choice.location_id != choice.location_id for other, other_choice in awake)
        # 誰かが言葉を口にしたか、一緒にいた人物が別の場所へ移る一時間だけ応じる(黙って同じ場所にいるだけなら、
        # 次の一時間に、さっきしていたこととして見える)
        if not choice.asked or not (spoke or left):
            return choice
        return _react(walker, choice, others)

    reacted = dict(zip([walker.id for walker in walkers], _parallel(react, walkers)))
    after = _people(walkers, hour, [reacted[walker.id].location_id for walker in walkers])
    groups: dict[int, list[_Walker]] = {}
    for walker in walkers:
        groups.setdefault(reacted[walker.id].location_id, []).append(walker)
    for walker in walkers:
        choice = reacted[walker.id]
        here = after.get(choice.location_id)
        awake = choice.kind != _SLEEP
        companions = [] if here is None else [person for person in here.people if person.character_id != walker.id]
        others = [(other, reacted[other.id]) for other in groups[choice.location_id] if other.id != walker.id]
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
        walker.seen = [_seen_deed(walker, other, other_choice, origins[other.id]) for other, other_choice in others]
        load = needs.hour_load(choice.deeds)
        walker.load += load
        walker.location_id = choice.location_id
        walker.needs = needs.next_needs(walker.needs, choice.kind, index, hours_per_day, walker.plan.profile, choice.ate)
        walker.hungers.append(walker.needs.hunger)
        walker.desires.append(walker.needs.desire)
        walker.append(_Entry(
            start=_clock(hour), end=_clock(hour), place=(here.location_name if here else None) or "",
            kind=choice.kind, text=choice.text, speech=choice.speech,
            others=[f"{other.name}: " + ("眠っている" if other_choice.kind == _SLEEP else _deed(other_choice))
                    for other, other_choice in others]), choice.asked)
        action = HourAction(
            character_id=walker.id, time=hour, location_id=choice.location_id, kind=choice.kind, text=choice.text,
            speech=choice.speech, thought=choice.thought, sleepiness=walker.needs.sleepiness, hunger=walker.needs.hunger,
            desire=walker.needs.desire, load=load, fixed_event_id=choice.fixed_event_id,
            fixed_episode_id=choice.fixed_episode_id)
        assert walker.plan.expansion_id is not None
        with writing(Writer.AI_APPEND, walker.plan.expansion_id):
            call(expansion_steps.save_actions, ActionsForm(expansion_id=walker.plan.expansion_id, actions=[action]))
        walker.actions += 1
    return after


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


def simulate_day(
    character_ids: list[int] | None = None, date: Stamp | str | None = None, nudge: str | None = None,
    seed: int | None = None, ai: AIClient = ai_client, parent_event_id: int | None = None,
) -> DayRun:
    """`SimulateDay` に当たる。動かせない人物は失敗として返し、ほかの人物の一日は動かす。一人の一時間が組めなくても、
    その人物を止めるだけで、ほかの人物は続ける(止めた人物の展開は failed で残り、足せた行は展開ごと取り消せる)。"""
    rng = random.Random(seed)
    run = DayRun()
    first_ids = list(character_ids or [])
    if first_ids:
        scope = call(story_steps.read_scope, ScopeForm(args={"character_id": first_ids[0]})).scope()
    else:
        scope = story_scope.current() or Scope()
    with story_scope.scoped(scope):
        plan = call(expansion_steps.plan_day, DayForm(
            character_ids=first_ids, date=Stamp.parse(date), parent_event_id=parent_event_id))
    run.failed += plan.failed
    if not plan.characters:
        return run
    # 動かす人物の暦で、その日の一時間を数える(暦の違う人物は段取りで外してある)
    scope = call(story_steps.read_scope, ScopeForm(args={"character_id": plan.characters[0].character_id})).scope()
    run.keep_scope(scope)
    with story_scope.scoped(scope):
        run.date = plan.date
        run.day_end = plan.day_end
        walkers = _walkers(ai, rng, plan, nudge)
        first_hour = Stamp.parse(plan.hours[0])
        assert first_hour is not None
        present = _people(walkers, first_hour, [walker.location_id for walker in walkers])
        for index in range(len(plan.hours)):
            active = [walker for walker in walkers if walker.failed is None]
            if not active:
                break
            try:
                present = _hour(active, index, plan, present)
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
