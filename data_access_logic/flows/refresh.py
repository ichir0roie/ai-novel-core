#!/usr/bin/env python3
"""後回しの AI の段と種の流れ(`RefreshGeneratedContent` / `ExtractEventSeeds`)。"""
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.flows import event_seed, speech
from data_access_logic.flows.summary import rewrite_event_summaries
from data_access_logic.source_text import SourceRow
from db.writer import generated


class RefreshedAll(BaseModel):
    events_summarized: int
    speeches_written: int


class ExtractedEventSeeds(BaseModel):
    seeds_added: int


@generated()
def refresh_generated_content(ai: AIClient = ai_client) -> RefreshedAll:
    """本文と食い違った要約をすべて作り直し、本文が変わった話のセリフを拾い直す。数は、作り直した要約・書いたセリフの件数。
    ミームの分類・アンチミームは、いまは回さない(`data_access_logic/readme.md` の「ミーム」)。"""
    return RefreshedAll(
        events_summarized=rewrite_event_summaries(ai, None),
        speeches_written=speech.refresh_stale(ai),
    )


@generated()
def extract_event_seeds(rows: list[SourceRow], ai: AIClient = ai_client) -> ExtractedEventSeeds:
    return ExtractedEventSeeds(seeds_added=event_seed.refresh_and_consolidate(ai, rows))
