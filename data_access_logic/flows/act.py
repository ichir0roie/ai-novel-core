#!/usr/bin/env python3
"""人物モードの流れ(`SimulateDay`)。渡した人物たちの一日を、0 時から暦の一時間ずつ動かし、行動の表(`event_action`)に残して、
一日の終わりに人物ごとの一日を出来事一件にまとめる。

- 一時間ごとに、人物ごとの手を並べて決める(人物どうしは並列)。作者の出来事・話の予定がある時間は予定で埋め、眠っている時間と
  眠気に負けた時間は規則で埋めて、人物の目(AI)には聞かない(`next_needs`)
- 手を決めたら、同じ場所に居合わせた人物どうしに、相手がこの一時間にしたことを見せて応じさせる(一往復)。次の一時間の材料には、
  目の前の人物がさっきしたことを渡す
- 動けるのは、人物のいるエリア(詳細の場所の一番近い、詳細でない上の場所)の詳細の場所のあいだだけ。詳細の場所にいない人物は動かさない
- 人物ごとに展開(`expansion`、mode=character)を一つ立て、書き手 `ai_append` で書くので、その一日の行動・出来事・来歴などは
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
from data_access_logic.ai_client import AIClient
from data_access_logic.caller import call
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.event_seed import steps as seed_steps
from data_access_logic.event_seed.extractor import draw_from
from data_access_logic.expansion import actor, budget
from data_access_logic.expansion import steps as expansion_steps
from data_access_logic.expansion.act_models import (
    ActFailure, ActionsForm, DayActed, DayBrief, DayBriefForm, DayCharacter, DayForm, DayMaterialForm, DayPlace,
    DayPlan, DayRequest, DayRun, DaySaveForm, HourAction, HourScene, MotivesForm, Needs, NewCharacterLink, PeopleForm,
    PlacePeople,
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


def next_needs(needs: Needs, kind: str, hours_per_day: int) -> Needs:
    """一時間を過ごしたあとの眠気と空腹。眠ると眠気が減り、起きていると増える。食べると空腹が 0 に戻る。
    増え方は一日 24 時間の暦の量で、一日の長さが違う暦では、一日あたりの量がそろうように割合を直す。"""
    scale = 24 / hours_per_day
    asleep = kind == _SLEEP
    change = constants.DAY_SLEEPINESS_ASLEEP_PER_HOUR if asleep else constants.DAY_SLEEPINESS_AWAKE_PER_HOUR
    sleepiness = min(100, max(0, needs.sleepiness + round(change * scale)))
    hunger = 0 if kind == "食べる" else min(100, needs.hunger + round(constants.DAY_HUNGER_PER_HOUR * scale))
    return Needs(sleepiness=sleepiness, hunger=hunger, asleep=asleep)


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
    """人物の一日の一行(続けて眠った時間は一行にまとめる)。"""

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
        return f"{span}: {self.place}で、{self.text}" + (f"「{self.speech}」" if self.speech else "")

    def for_author(self) -> str:
        return "\n".join([self.for_character(), *(f"  - {line}" for line in self.others)])


@dataclass
class _Walker:
    """一日を動いている人物の、流れの中の様子。"""

    plan: DayCharacter
    brief: DayBrief
    places: list[DayPlace]
    location_id: int
    needs: Needs
    entries: list[_Entry] = field(default_factory=list)
    # 目の前の人物が、さっきの一時間にしたこと(見る人の目で)
    seen: list[str] = field(default_factory=list)
    # 居合わせた人物(人物id と名前)。起きているあいだに同じ場所にいた人物
    met: dict[int, str | None] = field(default_factory=dict)
    # 居合わせて互いに応じた、動かしている相手
    met_walkers: dict[int, str] = field(default_factory=dict)
    awake_places: Counter[int] = field(default_factory=Counter)
    first_awake: Stamp | None = None
    actions: int = 0
    failed: str | None = None

    @property
    def id(self) -> int:
        return self.plan.character_id

    @property
    def name(self) -> str:
        return self.plan.name or ""

    def append(self, entry: _Entry) -> None:
        last = self.entries[-1] if self.entries else None
        if (last is not None and entry.kind == _SLEEP and last.kind == _SLEEP and last.place == entry.place
                and not entry.others and not last.others):
            last.end = entry.end
            return
        self.entries.append(entry)


@dataclass
class _Choice:
    """一時間の手。人物の目に聞いた手か、予定・規則で埋めた手。"""

    location_id: int
    kind: str
    text: str
    speech: str | None = None
    thought: str | None = None
    asked: bool = False
    fixed_event_id: int | None = None
    fixed_episode_id: int | None = None


def _seen_name(viewer: _Walker, character_id: int, name: str | None) -> str:
    return name if character_id in viewer.brief.known_ids and name else "名を知らない人"


def _scene(walker: _Walker, index: int, plan: DayPlan, here: PlacePeople | None) -> HourScene:
    hour = plan.hours[index]
    upcoming = [f"{_clock(plan.hours[slot.hour])}から: {slot.label}" for slot in walker.plan.fixed if slot.hour > index]
    return HourScene(
        time=hour, location_id=walker.location_id, location_name=None if here is None else here.location_name,
        needs=walker.needs, log=[entry.for_character() for entry in walker.entries[-constants.DAY_LOG_LIMIT:]],
        present=[] if here is None else [person for person in here.people if person.character_id != walker.id],
        seen=walker.seen, upcoming=upcoming, places=walker.places)


def _choose(ai: AIClient, walker: _Walker, index: int, plan: DayPlan, here: PlacePeople | None) -> _Choice:
    """予定があれば予定、眠っているか眠気に負けたら眠る。どれでもなければ人物の目に聞く。"""
    slot = walker.plan.fixed_at(index)
    if slot is not None:
        return _Choice(location_id=slot.location_id, kind=_FIXED, text=slot.label,
                       fixed_event_id=slot.event_id, fixed_episode_id=slot.episode_id)
    needs = walker.needs
    if needs.asleep and needs.sleepiness > constants.DAY_WAKE_BELOW:
        return _Choice(location_id=walker.location_id, kind=_SLEEP, text="眠っていた")
    if not needs.asleep and needs.sleepiness >= constants.DAY_SLEEP_FORCE:
        return _Choice(location_id=walker.plan.home_id, kind=_SLEEP, text="眠気に勝てず、寝床で眠った")
    draft = actor.hour_draft(ai, walker.brief, _scene(walker, index, plan, here))
    if draft is None:
        return _Choice(location_id=walker.location_id, kind="休む", text="その場でしばらく過ごした")
    place_ids = {place.id for place in walker.places}
    location_id = draft.location_id if draft.location_id in place_ids else walker.location_id
    return _Choice(location_id=location_id, kind=draft.kind, text=draft.action, speech=draft.speech,
                   thought=draft.thought, asked=True)


def _deed(choice: _Choice) -> str:
    return choice.text + (f"「{choice.speech}」" if choice.speech else "")


def _react(ai: AIClient, walker: _Walker, choice: _Choice, others: list[tuple[_Walker, _Choice]], index: int,
           plan: DayPlan, here: PlacePeople | None) -> _Choice:
    """同じ場所に居合わせた人物がこの一時間にしたことを見せて、応じさせる。応じた分を一時間の手に書き足す。"""
    seen = [f"{_seen_name(walker, other.id, other.name)}: "
            + ("眠っている" if other_choice.kind == _SLEEP else _deed(other_choice)) for other, other_choice in others]
    draft = actor.reaction_draft(ai, walker.brief, _scene(walker, index, plan, here), _deed(choice), seen)
    if draft is None:
        return choice
    speeches = [speech for speech in (choice.speech, draft.speech) if speech]
    thoughts = [thought for thought in (choice.thought, draft.thought) if thought]
    return _Choice(location_id=choice.location_id, kind=choice.kind, text=f"{choice.text}\n{draft.action}",
                   speech="\n".join(speeches) or None, thought="\n".join(thoughts) or None, asked=True)


def _hour(ai: AIClient, walkers: list[_Walker], index: int, plan: DayPlan) -> None:
    """全員の一時間を決めて、居合わせた人物どうしを応じさせ、行動の表に足す。"""
    hour = plan.hours[index]
    before = {place.location_id: place for place in call(expansion_steps.people_at, PeopleForm(
        time=hour, positions={walker.id: walker.location_id for walker in walkers}))}
    choices = _parallel(lambda walker: _choose(ai, walker, index, plan, before.get(walker.location_id)), walkers)
    decided = dict(zip([walker.id for walker in walkers], choices))
    after = {place.location_id: place for place in call(expansion_steps.people_at, PeopleForm(
        time=hour, positions={walker.id: choice.location_id for walker, choice in zip(walkers, choices)}))}
    groups: dict[int, list[_Walker]] = {}
    for walker in walkers:
        groups.setdefault(decided[walker.id].location_id, []).append(walker)

    def react(walker: _Walker) -> _Choice:
        choice = decided[walker.id]
        others = [(other, decided[other.id]) for other in groups[choice.location_id] if other.id != walker.id]
        if not choice.asked or not any(other_choice.kind != _SLEEP for _, other_choice in others):
            return choice
        return _react(ai, walker, choice, others, index, plan, after.get(choice.location_id))

    reacted = dict(zip([walker.id for walker in walkers], _parallel(react, walkers)))
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
            walker.met_walkers.update({other.id: other.name for other, other_choice in others
                                       if other_choice.kind != _SLEEP})
        walker.seen = [f"{_seen_name(walker, other.id, other.name)}: "
                       + ("眠っている" if other_choice.kind == _SLEEP else _deed(other_choice))
                       for other, other_choice in others] if awake else []
        walker.location_id = choice.location_id
        walker.needs = next_needs(walker.needs, choice.kind, len(plan.hours))
        walker.append(_Entry(
            start=_clock(hour), end=_clock(hour), place=(here.location_name if here else None) or "",
            kind=choice.kind, text=choice.text, speech=choice.speech,
            others=[f"{other.name}: " + ("眠っている" if other_choice.kind == _SLEEP else _deed(other_choice))
                    for other, other_choice in others]))
        action = HourAction(
            character_id=walker.id, time=hour, location_id=choice.location_id, kind=choice.kind, text=choice.text,
            speech=choice.speech, thought=choice.thought, sleepiness=walker.needs.sleepiness, hunger=walker.needs.hunger,
            fixed_event_id=choice.fixed_event_id, fixed_episode_id=choice.fixed_episode_id)
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


def _summary(acted: DayActed, walker: _Walker) -> str:
    lines = [f"{acted.name}(id={acted.character_id}) の一日: 行動 {acted.actions} 件",
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


def _record(ai: AIClient, rng: random.Random, walker: _Walker, plan: DayPlan) -> DayActed:
    """人物の一日を作者の目で記録し、出来事一件と、来歴・事柄・住まいの移動・思いの増減として足す。"""
    expansion_id = walker.plan.expansion_id
    assert expansion_id is not None
    date = Stamp.parse(plan.date)
    day_end = Stamp.parse(plan.day_end)
    assert date is not None and day_end is not None
    material = call(expansion_steps.day_material, DayMaterialForm(
        actor_id=walker.id, participant_ids=list(walker.met), date=date, day_end=day_end,
        home_id=walker.plan.home_id, parent_event_id=plan.parent_event_id))
    request = DayRequest(actor_name=walker.name, log=[entry.for_author() for entry in walker.entries],
                         present={walker.id: walker.name, **walker.met}, material=material)
    outcome = actor.judge_draft(ai, request)
    if outcome is None:
        raise ValueError("一日の記録が得られなかった")
    outcome = budget.clamp(outcome, material.frame, walker.id)
    time = walker.first_awake or date
    location_id = walker.awake_places.most_common(1)[0][0] if walker.awake_places else walker.plan.home_id
    with writing(Writer.AI_APPEND, expansion_id):
        saved = call(expansion_steps.save_day, DaySaveForm(
            actor_id=walker.id, time=time, end=day_end, location_id=location_id, participant_ids=list(walker.met),
            destinations=material.destinations, outcome=outcome, parent_event_id=plan.parent_event_id))
        created = []
        for draft in outcome.new_characters:
            record = character_flow.generate(ai, rng, location_id, time, draft.person, CharacterForm(text=draft.description))
            if record is None:
                logger.warning(f"現れる人物「{draft.description[:30]}」を作れなかった")
                continue
            call(expansion_steps.link_new_character, NewCharacterLink(
                actor_id=walker.id, character_id=record.id, event_id=saved.event.id,
                relation=draft.relation or "知り合い", time=time))
            created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=location_id))
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
    """人物ごとに一日の展開を立て、一日のあいだ変わらない人物の目の材料を読む。"""
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
        brief = call(expansion_steps.day_brief, DayBriefForm(
            character_id=character.character_id, time=date, seeds=draw_from(rng, pool), nudge=nudge))
        walkers.append(_Walker(plan=character, brief=brief, places=plan.places[character.area_id],
                               location_id=character.home_id, needs=character.needs))
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
        walkers = _walkers(ai, rng, plan, nudge)
        for index in range(len(plan.hours)):
            active = [walker for walker in walkers if walker.failed is None]
            if not active:
                break
            try:
                _hour(ai, active, index, plan)
            except Exception as error:
                for walker in active:
                    _fail(run, walker, error)
        survivors = [walker for walker in walkers if walker.failed is None]
        # 乱数は並べる前に人物ごとに分けておく(並べた先で一つの乱数を取り合わない)
        seeds = {walker.id: rng.randrange(2**31) for walker in survivors}

        def record(walker: _Walker) -> DayActed | Exception:
            try:
                return _record(ai, random.Random(seeds[walker.id]), walker, plan)
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
                id=walker.plan.expansion_id, summary=_summary(result, walker)))
            run.acted.append(result)
    return run
