#!/usr/bin/env python3
"""出来事の生成の流れ(`GenerateEvent`)。

db の段は `data_access_logic/event/steps.py`、
AI・乱数の段は `data_access_logic/event/progress.py` の `rolled_candidate` / `record_draft` と `writer.text_draft`。
"""
from __future__ import annotations

import random

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.character import steps as character_steps
from data_access_logic.character.moves import allowed_moves
from data_access_logic.event import progress, writer
from data_access_logic.event import steps as event_steps
from data_access_logic.event.form import EventForm
from data_access_logic.event.record import GeneratedEvent
from data_access_logic.event_seed import steps as seed_steps
from data_access_logic.event_seed.extractor import draw_from
from data_access_logic.step import RowId
from data_access_logic.flows import event_seed
from data_access_logic.caller import call
from data_access_logic.flows.summary import refresh


def _write_text(ai: AIClient, event_id: int) -> GeneratedEvent:
    """本文(text)の空いた出来事に、記録の本文だけを書く。書けなければ空のまま残す。居場所は移さない。"""
    refresh(ai, call(event_steps.text_targets, RowId(id=event_id)))
    material = call(event_steps.text_material, RowId(id=event_id))
    call(event_steps.save_event_text, event_steps.EventTextForm(event_id=event_id, draft=writer.text_draft(ai, material)))
    return GeneratedEvent.model_validate(call(event_steps.event_record, RowId(id=event_id)).model_dump())


def _progress(ai: AIClient, rng: random.Random, form: EventForm) -> GeneratedEvent:
    plan = call(event_steps.plan, form)
    seeds = draw_from(rng, call(seed_steps.seed_pool))
    situation_form = event_steps.SituationForm(
        location_id=plan.location_id, character_ids=plan.character_ids, time=plan.time, scene=form.scene)
    refresh(ai, call(event_steps.situation_targets, situation_form))
    current = call(event_steps.situation, situation_form)
    candidate = progress.rolled_candidate(ai, rng, current, seeds)
    if candidate is None:
        raise ValueError("出来事の候補が得られなかった")
    destinations = call(event_steps.destinations,
                        event_steps.DestinationsForm(location_id=plan.location_id, time=plan.time))
    draft = progress.record_draft(ai, current, destinations, candidate)
    if draft is None:
        raise ValueError("出来事の記録が得られなかった")
    record = call(event_steps.save_progress, event_steps.ProgressForm(
        situation=situation_form, destinations=destinations, draft=draft, event=form))
    # 記録の応答の移動先のうち、居合わせた人物と移動先の候補に当たるものだけで居場所を移す(空なら何もしない)
    moves = allowed_moves(draft.character_moves, plan.character_ids, [destination.id for destination in destinations])
    moved = call(character_steps.move_characters, character_steps.MovesForm(moves=moves, time=plan.time)) if moves else []
    return GeneratedEvent.model_validate({**record.model_dump(), "moves": moved})


def generate_event(event: EventForm | None = None, seed: int | None = None, ai: AIClient = ai_client) -> GeneratedEvent:
    """`GenerateEvent` に当たる。足した出来事の本文も種の元になるので、書き戻したあとで種を抜き出す。
    レスポンスの `moves` は、この出来事で居場所を移した人物の移動先。"""
    form = event or EventForm()
    record = _write_text(ai, form.id) if form.id is not None else _progress(ai, random.Random(seed), form)
    event_seed.refresh_and_consolidate(ai)
    return record
