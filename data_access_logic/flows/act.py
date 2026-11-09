#!/usr/bin/env python3
"""人物モードの流れ(`ActCharacter`)。人物が自分の知ることから一手を決め、巻きこみたい相手がいれば言葉を交わし、
実行の中の手をまとめて作者の目で裁いて世界に足す。
一手の前後に、動く人物か居合わせる人物が出るプロットつきの話があれば、狙う段の前に語り部が入り、そのプロットを動機にして
人物の外の状況を整え、裁く段にプロットと動機を渡して、プロットに逆らう記録にさせない。

db の段は `data_access_logic/expansion/steps.py`、AI の段は `data_access_logic/expansion/actor.py`。
狙う段と対話の手番は手ごとに順に(並列にしない)一番安いモデルで回し、裁く段は実行ごとに一度だけ強いモデルで回す。
動ける人物・巻きこめる相手・裁いた結果の幅は、気力・手数・影響の枠(`expansion/budget.py`)で縛る。
一手ごとに展開(`expansion`、mode=character)を一つ立て、書き手 `ai_append`(足すことと、`end` で終わりを付けることだけ)で書くので、
足した行は展開の記録に残り、`RevertExpansion` で一手ずつ取り消せる。ミームは抜き出さない(話の本文の確定のあとにだけ抜き出す)。
"""
from __future__ import annotations

import logging
import random

from ai.claude_code import ai_client
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.caller import call
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.event import steps as event_steps
from data_access_logic.event_seed import steps as seed_steps
from data_access_logic.event_seed.extractor import draw_from
from data_access_logic.expansion import actor, budget
from data_access_logic.expansion import steps as expansion_steps
from data_access_logic.expansion.act_models import (
    ActedCharacter, ActFailure, ActFrameForm, ActOutcomeDraft, ActorPick, ActPlan, ActRun, ActSaveForm,
    DialogueBriefForm, DialogueTurn, IntentDraft, InviteForm, MotivesForm, Narration, NewCharacterLink,
    OutcomeRequest,
)
from data_access_logic.expansion.form import ExpansionCreateForm, ExpansionFinishForm
from data_access_logic.flows import character as character_flow
from data_access_logic.flows.summary import refresh
from db.schema import ExpansionMode
from db.stamp import Stamp
from db.writer import Writer, writing

logger = logging.getLogger(__name__)


def _summary(acted: ActedCharacter) -> str:
    pick = acted.actor
    lines = [f"{pick.name}(id={pick.character_id}) {pick.time}: {acted.intent.aim}", f"成り行き: {acted.roll}",
             f"出来事: {acted.event.name}(id={acted.event.id})"]
    if acted.invited_ids:
        names = [turn.name for turn in acted.dialogue if turn.character_id in acted.invited_ids]
        lines.append(f"巻きこんだ相手: {', '.join(dict.fromkeys(name or '' for name in names))}"
                     f"(手番 {len(acted.dialogue) - 1})")
    if acted.arc_id is not None:
        lines.append(f"企て: id={acted.arc_id}")
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
        lines.append(f"影響力: {acted.frame.influence} 気力: {pick.energy}")
    if acted.narration is not None:
        lines.append(f"語り部: {', '.join(f'ep{episode.id}' for episode in acted.narration.episodes)} のプロットを動機にした")
    return "\n".join(lines)


def _prompt_text(intent: IntentDraft, dialogue: list[DialogueTurn], narration: Narration | None) -> str:
    """展開に残す人物の狙い。語り部が入ったら動機・語り・要求を頭に、対話があれば手番を起きた順に添える(取り消しの前に読み返せるように)。
    巻きこんだ相手とのやり取りは最後に置く(見取り図がその見出しから後を手番として読む)。"""
    lines = [*([] if narration is None else [narration.as_text()]), intent.as_text()]
    if len(dialogue) > 1:
        lines += ["巻きこんだ相手とのやり取り:", *(f"- {turn.as_text()}" for turn in dialogue[1:])]
    return "\n".join(lines)


def _narration(ai: AIClient, pick: ActorPick, nudge: str | None) -> Narration | None:
    """一手の前後に関わる話があれば、語り部にプロットを動機にして場を整えさせる。語り部の答えが得られなくても、
    前後の話のプロットは裁く段に渡す(プロットに逆らわせない守りは外さない)。"""
    brief = call(expansion_steps.narrator_brief, expansion_steps.NarratorBriefForm(pick=pick, nudge=nudge))
    if not brief.episodes:
        return None
    draft = actor.narration_draft(ai, brief)
    if draft is None:
        return Narration(episodes=brief.episodes)
    return Narration(episodes=brief.episodes, motivation=draft.motivation, narration=draft.narration,
                     request=draft.request)


def _dialogue(ai: AIClient, pick: ActorPick, intent: IntentDraft, invited_ids: list[int],
              narration: Narration | None) -> list[DialogueTurn]:
    """動いた人物の一手を口火に、巻きこんだ相手と動いた人物に交互に手番を回す。並列にはしない。
    誰かが話を終える(動いた人物なら対話ごと、相手ならその相手だけが抜ける)か、手番が上限に達したら止める。"""
    time = Stamp.parse(pick.time)
    assert time is not None
    participants = [pick.character_id, *invited_ids]
    refresh(ai, call(expansion_steps.motive_targets, MotivesForm(character_ids=invited_ids, time=time)))
    told = None if narration is None else narration.narration
    briefs = {id_: call(expansion_steps.dialogue_brief, DialogueBriefForm(
        character_id=id_, time=time, location_id=pick.location_id, participant_ids=participants,
        mentioned="\n".join([intent.as_text(), told or ""]), narration=told)) for id_ in participants}
    turns = [DialogueTurn(character_id=pick.character_id, name=pick.name, thought=intent.inner, action=intent.action,
                          speech=intent.speech, aim=intent.aim)]
    actor_request = (f"あなたはこの狙いで動いている: {intent.aim}。相手の返事を受けて、次の一手を返す。"
                     "狙いを果たしたか、あきらめたなら done を true にする。")
    invitee_request = "目の前のやり取りに、あなたの一手を返す。話を切り上げる・断って立ち去るなら done を true にする。"
    active = list(invited_ids)
    while active and len(turns) - 1 < constants.ACT_DIALOGUE_TURN_LIMIT:
        for character_id in [*active, pick.character_id]:
            if len(turns) - 1 >= constants.ACT_DIALOGUE_TURN_LIMIT:
                break
            is_actor = character_id == pick.character_id
            turn = actor.turn_draft(ai, briefs[character_id], turns, actor_request if is_actor else invitee_request)
            if turn is None:
                return turns
            turns.append(turn)
            if turn.done:
                if is_actor:
                    return turns
                active.remove(character_id)
    return turns


def _plan(ai: AIClient, rng: random.Random, pick: ActorPick, expansion_id: int, nudge: str | None,
          used_ids: list[int]) -> ActPlan:
    time = Stamp.parse(pick.time)
    assert time is not None
    seeds = draw_from(rng, call(seed_steps.seed_pool))
    refresh(ai, call(expansion_steps.motive_targets, MotivesForm(character_ids=[pick.character_id], time=time)))
    narration = _narration(ai, pick, nudge)
    brief = call(expansion_steps.actor_brief, expansion_steps.BriefForm(
        pick=pick, seeds=seeds, nudge=nudge, narration=narration))
    intent = actor.intent_draft(ai, brief)
    if intent is None:
        raise ValueError("人物の一手が得られなかった")
    invited_ids = call(expansion_steps.invitable, InviteForm(
        actor_id=pick.character_id, time=time, location_id=pick.location_id,
        candidate_ids=[invite.character_id for invite in intent.invites], exclude_ids=used_ids)) if intent.invites else []
    dialogue = _dialogue(ai, pick, intent, invited_ids, narration) if invited_ids else []
    call(expansion_steps.note_prompt, expansion_steps.PromptForm(
        expansion_id=expansion_id, prompt=_prompt_text(intent, dialogue, narration)))

    present_ids = list(dict.fromkeys([*brief.present_ids, *invited_ids]))
    # 場面(状況の材料を引く文)には人物に見えた語りまでを入れ、語り部の動機とプロットは入れない(裁く段へは別の見出しで渡す)
    told = None if narration is None else narration.narration
    scene = "\n".join([*([] if told is None else [f"語り部の語り: {told}"]), _prompt_text(intent, dialogue, None)])
    situation_form = event_steps.SituationForm(
        location_id=pick.location_id, character_ids=[pick.character_id, *present_ids], time=time, scene=scene)
    refresh(ai, call(event_steps.situation_targets, situation_form))
    situation = call(event_steps.situation, situation_form)
    destinations = call(event_steps.destinations,
                        event_steps.DestinationsForm(location_id=pick.location_id, time=time))
    roll = rng.choice(constants.ACT_OUTCOMES)
    frame = call(expansion_steps.act_frame, ActFrameForm(
        actor_id=pick.character_id, participant_ids=[pick.character_id, *present_ids], time=time, roll=roll))
    motivations = call(expansion_steps.participant_motivations, MotivesForm(
        character_ids=[pick.character_id, *present_ids], time=time))
    arc = next((arc for arc in brief.arcs if arc.id == intent.arc_id), None)
    return ActPlan(expansion_id=expansion_id, pick=pick, intent=intent, present_ids=present_ids,
                   invited_ids=invited_ids, request=OutcomeRequest(
                       situation=situation, destinations=destinations, actor_name=pick.name, intent=intent,
                       roll=roll, arc=arc, dialogue=dialogue[1:], frame=frame, motivations=motivations,
                       narration=narration))


def _save(ai: AIClient, rng: random.Random, plan: ActPlan, outcome: ActOutcomeDraft) -> ActedCharacter:
    pick, request = plan.pick, plan.request
    time = Stamp.parse(pick.time)
    assert time is not None
    outcome = budget.clamp(outcome, request.frame, pick.character_id)
    saved = call(expansion_steps.save_act, ActSaveForm(
        actor_id=pick.character_id, time=time, location_id=pick.location_id, participant_ids=plan.present_ids,
        destinations=request.destinations, intent=plan.intent, outcome=outcome))
    created = []
    for draft in outcome.new_characters:
        record = character_flow.generate(ai, rng, pick.location_id, time, draft.person, CharacterForm(text=draft.description))
        if record is None:
            logger.warning(f"現れる人物「{draft.description[:30]}」を作れなかった")
            continue
        call(expansion_steps.link_new_character, NewCharacterLink(
            actor_id=pick.character_id, character_id=record.id, event_id=saved.event.id,
            relation=draft.relation or "知り合い", time=time))
        created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=pick.location_id))
    dialogue = [DialogueTurn(character_id=pick.character_id, name=pick.name, thought=plan.intent.inner,
                             action=plan.intent.action, speech=plan.intent.speech, aim=plan.intent.aim),
                *request.dialogue] if request.dialogue else []
    return ActedCharacter(expansion_id=plan.expansion_id, actor=pick, intent=plan.intent, roll=request.roll,
                          event=saved.event, arc_id=saved.arc_id, idea_ids=saved.idea_ids, characters=created,
                          moves=saved.moves, motivations=saved.motivations, invited_ids=plan.invited_ids,
                          dialogue=dialogue, frame=request.frame, narration=request.narration)


def _failed(run: ActRun, expansion_id: int | None, pick: ActorPick | None, error: Exception) -> None:
    if expansion_id is not None:
        call(expansion_steps.finish_expansion, ExpansionFinishForm(id=expansion_id, status="failed"))
    run.failed.append(ActFailure(expansion_id=expansion_id, character_id=None if pick is None else pick.character_id,
                                 name=None if pick is None else pick.name, error=str(error)))


def act_character(
    character_id: int | None = None, time: Stamp | str | None = None, nudge: str | None = None,
    seed: int | None = None, act_count: int = 1, ai: AIClient = ai_client,
) -> ActRun:
    """`ActCharacter` に当たる。`character_id` は一手目の人物で、二手目からは入口が引く(同じ実行で同じ人物は二度動かない)。
    手ごとに失敗を記録して次へ進む(失敗した手の展開は failed で残り、足せた行は展開ごと取り消せる)。"""
    if not 1 <= act_count <= constants.ACT_RUN_LIMIT:
        raise ValueError(f"act_count は 1〜{constants.ACT_RUN_LIMIT}")
    rng = random.Random(seed)
    run = ActRun()
    plans: list[ActPlan] = []
    used_ids: list[int] = []
    for index in range(act_count):
        try:
            pick = call(expansion_steps.pick_actor, expansion_steps.PickForm(
                character_id=character_id if index == 0 else None, time=Stamp.parse(time),
                seed=rng.randrange(2**31), exclude_ids=used_ids))
        except ValueError as error:
            _failed(run, None, None, error)
            continue
        expansion = call(expansion_steps.start_expansion, ExpansionCreateForm(
            mode=ExpansionMode.CHARACTER, actor_id=pick.character_id, time=Stamp.parse(pick.time),
            location_id=pick.location_id))
        try:
            with writing(Writer.AI_APPEND, expansion.id):
                plan = _plan(ai, rng, pick, expansion.id, nudge, used_ids)
        except Exception as error:
            logger.exception(f"{pick.name}(id={pick.character_id})の一手を組めなかった")
            _failed(run, expansion.id, pick, error)
            continue
        plans.append(plan)
        used_ids += [pick.character_id, *plan.invited_ids]
    if not plans:
        return run

    plans.sort(key=lambda plan: Stamp.parse(plan.pick.time) or Stamp(1))
    judged = actor.judge_draft(ai, [plan.request for plan in plans])
    outcomes = {} if judged is None else {item.act_number: item.outcome() for item in judged.outcomes}
    for number, plan in enumerate(plans, start=1):
        outcome = outcomes.get(number)
        if outcome is None:
            _failed(run, plan.expansion_id, plan.pick, ValueError("裁いた記録が得られなかった"))
            continue
        try:
            with writing(Writer.AI_APPEND, plan.expansion_id):
                acted = _save(ai, rng, plan, outcome)
        except Exception as error:
            logger.exception(f"{plan.pick.name}(id={plan.pick.character_id})の一手を足せなかった")
            _failed(run, plan.expansion_id, plan.pick, error)
            continue
        call(expansion_steps.finish_expansion, ExpansionFinishForm(id=plan.expansion_id, summary=_summary(acted)))
        run.acted.append(acted)
    return run
