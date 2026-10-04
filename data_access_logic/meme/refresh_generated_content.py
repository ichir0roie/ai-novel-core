#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code import ai_client
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.meme.extractor import refresh as refresh_memes
from data_access_logic.summary_targets import rewrite_episode_summaries, rewrite_event_summaries
from db.schema import get_env_session

__all__ = ["RefreshGeneratedContent"]


class RefreshedAll(BaseModel):
    memes_added: int
    events_summarized: int
    episodes_summarized: int


class RefreshGeneratedContent(Entrypoint):
    # 数は、作り直した要約の件数(web の `web_session/refresh.py` と同じ)
    def result(self) -> RefreshedAll:
        with get_env_session() as s:
            return RefreshedAll(
                memes_added=refresh_memes(s, ai_client),
                events_summarized=rewrite_event_summaries(s, ai_client, None),
                episodes_summarized=len(rewrite_episode_summaries(s, ai_client, None)),
            )
