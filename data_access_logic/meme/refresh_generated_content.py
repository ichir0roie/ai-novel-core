#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select

from ai.claude_code import ai_client
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.episode import summary as episode_summary
from data_access_logic.event import summary as event_summary
from data_access_logic.meme.extractor import refresh as refresh_memes
from db.schema import Episode, Event, get_env_session

__all__ = ["RefreshGeneratedContent"]


class RefreshedAll(BaseModel):
    memes_added: int
    events_summarized: int
    episodes_summarized: int


class RefreshGeneratedContent(Entrypoint):
    def result(self) -> RefreshedAll:
        with get_env_session() as s:
            memes_added = refresh_memes(s, ai_client)
            events_summarized = sum(
                1 for event in s.scalars(select(Event)).all()
                if event_summary.summarize(s, ai_client, event) is not None)
            episodes_summarized = sum(
                1 for episode in s.scalars(select(Episode)).all()
                if episode_summary.summarize(s, ai_client, episode) is not None)
            return RefreshedAll(memes_added=memes_added, events_summarized=events_summarized,
                                episodes_summarized=episodes_summarized)
