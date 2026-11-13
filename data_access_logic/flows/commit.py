#!/usr/bin/env python3
"""行を確定したあと AI の段を追いかける流れ(`CommitEvent` / `UpdateEvent` / `CommitOracle` の `run()`)。

確定は db の段一つで済ませる(GUI の API が呼ぶ `execute(s)` と同じ)。そのあとの AI の段(要約・事実確認)は、
AI が答えなくても確定は残る。ミームと出来事の種は、いまは抜き出さない(`data_access_logic/readme.md` の「ミーム」「出来事の種」)。
"""
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.event import steps as event_steps
from data_access_logic.event.form import EventCreateForm, EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.oracle import steps as oracle_steps
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.step import RowId
from data_access_logic.flows.fact_check import check
from data_access_logic.caller import call
from data_access_logic.flows.summary import rewrite_event_summaries
from db.writer import generated


def commit_event(event: EventCreateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.commit_event, event)
    with generated():
        rewrite_event_summaries(ai, [record.id])
    return record


def update_event(event: EventUpdateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.update_event, event)
    with generated():
        rewrite_event_summaries(ai, [record.id])
    return record


def commit_oracle(oracle: OracleCreateForm, fact_check: bool = True, ai: AIClient = ai_client) -> OracleRecord:
    committed = call(oracle_steps.commit_oracle, oracle)
    if fact_check and committed.text.strip():
        with generated():
            check(ai, "oracle", ids=[committed.id])
    return call(oracle_steps.oracle_record, RowId(id=committed.id))
