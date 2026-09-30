#!/usr/bin/env python3
"""出来事の生成を、API 越しに回す。

引数は `data_access_logic/event/generate_event.py` の入口(`GenerateEvent`)と同じ。db の段は `data_access_logic/event/steps.py`、
AI・乱数の段は `data_access_logic/event/progress.py` の `rolled_candidate` / `record_draft` と `writer.text_draft`。
"""
from __future__ import annotations

import random

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.event import progress, writer
from data_access_logic.event import steps as event_steps
from data_access_logic.event.form import EventForm
from data_access_logic.event.record import EventRecord
from data_access_logic.event_seed import steps as seed_steps
from data_access_logic.event_seed.extractor import draw_from
from data_access_logic.step import RowId
from web_session import event_seed
from web_session.api import call
from web_session.summary import refresh


def _write_text(ai: AIClient, event_id: int) -> EventRecord:
    """本文(text)の空いた出来事に、記録の本文だけを書く。書けなければ空のまま残す。"""
    refresh(ai, call(event_steps.text_targets, RowId(id=event_id)))
    material = call(event_steps.text_material, RowId(id=event_id))
    call(event_steps.save_event_text, event_steps.EventTextForm(event_id=event_id, draft=writer.text_draft(ai, material)))
    return call(event_steps.event_record, RowId(id=event_id))


def _progress(ai: AIClient, rng: random.Random, form: EventForm) -> EventRecord:
    plan = call(event_steps.plan, form)
    seeds = draw_from(rng, call(seed_steps.seed_pool))
    situation_form = event_steps.SituationForm(
        location_id=plan.location_id, character_ids=plan.character_ids, time=plan.time, scene=form.scene)
    refresh(ai, call(event_steps.situation_targets, situation_form))
    current = call(event_steps.situation, situation_form)
    candidate = progress.rolled_candidate(ai, rng, current, seeds)
    if candidate is None:
        raise ValueError("出来事の候補が得られなかった")
    moves = call(event_steps.destinations, event_steps.DestinationsForm(location_id=plan.location_id, time=plan.time))
    draft = progress.record_draft(ai, current, moves, candidate, False)
    if draft is None:
        raise ValueError("出来事の候補が得られなかった")
    return call(event_steps.save_progress, event_steps.ProgressForm(
        situation=situation_form, destinations=moves, draft=draft, event=form))


def generate_event(event: EventForm | None = None, seed: int | None = None, ai: AIClient = ai_client) -> EventRecord:
    """`GenerateEvent` に当たる。足した出来事の本文も種の元になるので、書き戻したあとで種を抜き出す。"""
    form = event or EventForm()
    record = _write_text(ai, form.id) if form.id is not None else _progress(ai, random.Random(seed), form)
    event_seed.refresh_and_consolidate(ai)
    return record
