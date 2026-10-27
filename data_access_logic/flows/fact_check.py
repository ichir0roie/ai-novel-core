#!/usr/bin/env python3
"""事実確認の流れ。

AI の結果は束ごとに、得たその場で書き戻す。
"""
from __future__ import annotations

import logging

from ai.claude_code import fact_checker
from data_access_logic.ai_client import AIClient
from data_access_logic.fact_check import steps as fact_steps
from data_access_logic.source_text import SourceRow, batches
from data_access_logic.caller import call
from db.writer import generated

logger = logging.getLogger(__name__)


def check(ai: AIClient, table: str, ids: list[int] | None = None, limit: int | None = None) -> list[SourceRow]:
    """検めた行(検証結果を書き足した行)を返す。"""
    sources = call(fact_steps.check_sources, fact_steps.CheckScope(table=table, ids=ids, limit=limit))
    written: list[SourceRow] = []
    for batch in batches(sources, fact_checker.BATCH_LETTERS):
        notes = fact_checker.check_draft(ai, batch)
        if notes is None:
            continue
        call(fact_steps.save_fact_checks, fact_steps.NotesForm(notes=notes))
        written += [SourceRow(table=note.table, id=note.id) for note in notes]
    if sources:
        logger.info(f"{table} {len(sources)}件のうち、{len(written)}件を検めた")
    return written


@generated()
def check_facts(ai: AIClient, table: str, ids: list[int] | None, limit: int | None) -> fact_checker.FactChecked:
    return fact_checker.FactChecked(checked=len(check(ai, table, ids, limit)))
