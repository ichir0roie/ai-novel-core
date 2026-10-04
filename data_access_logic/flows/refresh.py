#!/usr/bin/env python3
"""後回しの AI の段とミーム・事実確認の流れ(`RefreshGeneratedContent` / `ExtractMemes` / `CheckFacts`)。"""
from __future__ import annotations

from ai.claude_code import ai_client, fact_checker
from data_access_logic.ai_client import AIClient
from pydantic import BaseModel

from data_access_logic.flows import meme
from data_access_logic.flows.fact_check import check_and_extract
from data_access_logic.flows.fact_check import extract_memes as extract_and_check_memes
from data_access_logic.flows.summary import rewrite_episode_summaries, rewrite_event_summaries


class RefreshedAll(BaseModel):
    memes_added: int
    events_summarized: int
    episodes_summarized: int


class ExtractedMemes(BaseModel):
    memes_added: int


def refresh_generated_content(ai: AIClient = ai_client) -> RefreshedAll:
    """`meme_seeded=false` の行からミームを抜き出し、本文と食い違った要約をすべて作り直す。数は、作り直した要約の件数。"""
    return RefreshedAll(
        memes_added=meme.refresh(ai),
        events_summarized=rewrite_event_summaries(ai, None),
        episodes_summarized=len(rewrite_episode_summaries(ai, None)),
    )


def extract_memes(fact_check: bool = True, ai: AIClient = ai_client) -> ExtractedMemes:
    return ExtractedMemes(memes_added=extract_and_check_memes(ai, fact_check))


def check_facts(table: str, ids: list[int] | None = None, limit: int | None = None,
                ai: AIClient = ai_client) -> fact_checker.FactChecked:
    if table not in fact_checker.MODELS:
        raise ValueError(f"table は {'/'.join(fact_checker.MODELS)} のいずれか: {table!r}")
    return check_and_extract(ai, table, ids, limit)
