#!/usr/bin/env python3
"""事実確認の流れ。

AI の結果は束ごとに、得たその場で書き戻す。
"""
from __future__ import annotations

import logging

from ai.claude_code import fact_checker
from data_access_logic.ai_client import AIClient
from data_access_logic.fact_check import steps as fact_steps
from data_access_logic.source_text import batches
from data_access_logic.flows import meme
from data_access_logic.caller import call

logger = logging.getLogger(__name__)


def check(ai: AIClient, table: str, ids: list[int] | None = None, limit: int | None = None) -> int:
    """検めた件数を返す。"""
    sources = call(fact_steps.check_sources, fact_steps.CheckScope(table=table, ids=ids, limit=limit))
    written = 0
    for batch in batches(sources, fact_checker.BATCH_LETTERS):
        notes = fact_checker.check_draft(ai, batch)
        if notes is None:
            continue
        written += call(fact_steps.save_fact_checks, fact_steps.NotesForm(notes=notes))
    if sources:
        logger.info(f"{table} {len(sources)}件のうち、{written}件を検めた")
    return written


def check_new_memes(ai: AIClient, last_id: int) -> int:
    """`last_id` より後に足したミームだけを検める。"""
    ids = call(fact_steps.new_meme_ids, fact_steps.LastMemeId(last_id=last_id))
    return check(ai, "meme", ids=ids) if ids else 0


def extract_memes(ai: AIClient, fact_check: bool) -> int:
    """ミームを抜き出し、`fact_check` なら足したミームも検める。足したミームの件数を返す。"""
    last_id = call(fact_steps.last_meme_id)
    added = meme.refresh(ai)
    if fact_check:
        check_new_memes(ai, last_id)
    return added


def check_and_extract(ai: AIClient, table: str, ids: list[int] | None, limit: int | None) -> fact_checker.FactChecked:
    """検めたあと、ミームの元(oracle)なら本文(検証結果の節を含む)からミームを抜き出し、足したミームも検める。"""
    checked = check(ai, table, ids, limit)
    if table == "meme":
        return fact_checker.FactChecked(checked=checked, memes_added=0)
    return fact_checker.FactChecked(checked=checked, memes_added=extract_memes(ai, fact_check=True))
