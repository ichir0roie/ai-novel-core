#!/usr/bin/env python3
"""人物モードの流れ(`ActCharacter`)。人物が自分の知ることから一手を決め、作者の目でその結果を裁いて世界に足す。

db の段は `data_access_logic/expansion/steps.py`、AI の段は `data_access_logic/expansion/actor.py` の `intent_draft` / `outcome_draft`。
一手ごとに展開(`expansion`、mode=character)を一つ立て、書き手 `ai_append`(足すことと、`end` で終わりを付けることだけ)で書くので、
足した行は展開の記録に残り、`RevertExpansion` で取り消せる。ミームは抜き出さない(話の本文の確定のあとにだけ抜き出す)。
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
from data_access_logic.expansion import actor
from data_access_logic.expansion import steps as expansion_steps
from data_access_logic.expansion.act_models import (
    ActedCharacter, ActorPick, ActSaveForm, IntentDraft, NewCharacterLink, OutcomeRequest,
)
from data_access_logic.expansion.form import ExpansionCreateForm, ExpansionFinishForm
from data_access_logic.flows import character as character_flow
from data_access_logic.flows.summary import refresh
from db.schema import ExpansionMode
from db.stamp import Stamp
from db.writer import Writer, writing

logger = logging.getLogger(__name__)


def _summary(pick: ActorPick, intent: IntentDraft, roll: str, acted: ActedCharacter) -> str:
    lines = [f"{pick.name}(id={pick.character_id}) {pick.time}: {intent.aim}", f"成り行き: {roll}",
             f"出来事: {acted.event.name}(id={acted.event.id})"]
    if acted.arc_id is not None:
        lines.append(f"企て: id={acted.arc_id}")
    if acted.idea_ids:
        lines.append(f"事柄: アイデア id={', '.join(map(str, acted.idea_ids))}")
    if acted.characters:
        lines.append(f"現れた人物: {', '.join(f'{c.name}(id={c.id})' for c in acted.characters)}")
    if acted.moves:
        lines.append(f"居場所の移動: {len(acted.moves)} 人")
    return "\n".join(lines)


def _act(ai: AIClient, rng: random.Random, pick: ActorPick, expansion_id: int, nudge: str | None) -> ActedCharacter:
    time = Stamp.parse(pick.time)
    assert time is not None
    seeds = draw_from(rng, call(seed_steps.seed_pool))
    brief = call(expansion_steps.actor_brief, expansion_steps.BriefForm(pick=pick, seeds=seeds, nudge=nudge))
    intent = actor.intent_draft(ai, brief)
    if intent is None:
        raise ValueError("人物の一手が得られなかった")
    call(expansion_steps.note_prompt, expansion_steps.PromptForm(expansion_id=expansion_id, prompt=intent.as_text()))

    situation_form = event_steps.SituationForm(
        location_id=pick.location_id, character_ids=[pick.character_id, *brief.present_ids], time=time,
        scene=intent.as_text())
    refresh(ai, call(event_steps.situation_targets, situation_form))
    situation = call(event_steps.situation, situation_form)
    destinations = call(event_steps.destinations,
                        event_steps.DestinationsForm(location_id=pick.location_id, time=time))
    roll = rng.choice(constants.ACT_OUTCOMES)
    arc = next((arc for arc in brief.arcs if arc.id == intent.arc_id), None)
    outcome = actor.outcome_draft(ai, OutcomeRequest(
        situation=situation, destinations=destinations, actor_name=pick.name, intent=intent, roll=roll, arc=arc))
    if outcome is None:
        raise ValueError("一手の記録が得られなかった")

    saved = call(expansion_steps.save_act, ActSaveForm(
        actor_id=pick.character_id, time=time, location_id=pick.location_id, participant_ids=brief.present_ids,
        destinations=destinations, intent=intent, outcome=outcome))
    created = []
    for draft in outcome.new_characters[:constants.ACT_NEW_CHARACTER_LIMIT]:
        record = character_flow.generate(ai, rng, pick.location_id, time, draft.person, CharacterForm(text=draft.description))
        if record is None:
            logger.warning(f"現れる人物「{draft.description[:30]}」を作れなかった")
            continue
        call(expansion_steps.link_new_character, NewCharacterLink(
            actor_id=pick.character_id, character_id=record.id, event_id=saved.event.id,
            relation=draft.relation or "知り合い", time=time))
        created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=pick.location_id))
    return ActedCharacter(expansion_id=expansion_id, actor=pick, intent=intent, roll=roll, event=saved.event,
                          arc_id=saved.arc_id, idea_ids=saved.idea_ids, characters=created, moves=saved.moves)


def act_character(
    character_id: int | None = None, time: Stamp | str | None = None, nudge: str | None = None,
    seed: int | None = None, ai: AIClient = ai_client,
) -> ActedCharacter:
    """`ActCharacter` に当たる。途中で止まったら、展開を failed にして止める(足せた行は残り、展開ごと取り消せる)。"""
    rng = random.Random(seed)
    pick = call(expansion_steps.pick_actor, expansion_steps.PickForm(
        character_id=character_id, time=Stamp.parse(time), seed=rng.randrange(2**31)))
    expansion = call(expansion_steps.start_expansion, ExpansionCreateForm(
        mode=ExpansionMode.CHARACTER, actor_id=pick.character_id, time=Stamp.parse(pick.time),
        location_id=pick.location_id))
    try:
        with writing(Writer.AI_APPEND, expansion.id):
            acted = _act(ai, rng, pick, expansion.id, nudge)
    except Exception:
        call(expansion_steps.finish_expansion, ExpansionFinishForm(id=expansion.id, status="failed"))
        raise
    call(expansion_steps.finish_expansion, ExpansionFinishForm(
        id=expansion.id, summary=_summary(pick, acted.intent, acted.roll, acted)))
    return acted
