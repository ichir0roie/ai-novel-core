#!/usr/bin/env python3
"""後回しの AI の段と種の流れ(`RefreshGeneratedContent` / `ExtractEventSeeds`)。"""
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.flows import event_seed, meme
from data_access_logic.flows.summary import rewrite_event_summaries
from data_access_logic.source_text import SourceRow
from db.writer import generated


class RefreshedAll(BaseModel):
    memes_added: int
    events_summarized: int


class ExtractedEventSeeds(BaseModel):
    seeds_added: int


@generated()
def refresh_generated_content(ai: AIClient = ai_client) -> RefreshedAll:
    """分類の空いたミームに分類を、対の無いミームにアンチミームを足し、本文と食い違った要約をすべて作り直す。
    数は、足したアンチミームと作り直した要約の件数。"""
    return RefreshedAll(
        memes_added=meme.refresh(ai, []),
        events_summarized=rewrite_event_summaries(ai, None),
    )


@generated()
def extract_event_seeds(rows: list[SourceRow], ai: AIClient = ai_client) -> ExtractedEventSeeds:
    return ExtractedEventSeeds(seeds_added=event_seed.refresh_and_consolidate(ai, rows))
