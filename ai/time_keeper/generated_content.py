#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from data_access_logic.meme.extractor import refresh as refresh_memes
from data_access_logic.episode import summary as episode_summary
from data_access_logic.event import summary as event_summary
from ai.time_keeper._ai import AIClient
from db.schema import Episode, Event, Session


def refresh(session: Session, ai: AIClient, record: Event | Episode | None = None) -> dict:
    memes_added = refresh_memes(session, ai)
    summarized = False
    if isinstance(record, Event):
        summarized = event_summary.summarize(session, ai, record) is not None
    elif isinstance(record, Episode):
        summarized = episode_summary.summarize(session, ai, record) is not None
    return {"memes_added": memes_added, "summarized": summarized}


def refresh_all(session: Session, ai: AIClient) -> dict:
    memes_added = refresh_memes(session, ai)
    events_summarized = sum(
        1 for event in session.scalars(select(Event)).all()
        if event_summary.summarize(session, ai, event) is not None)
    episodes_summarized = sum(
        1 for episode in session.scalars(select(Episode)).all()
        if episode_summary.summarize(session, ai, episode) is not None)
    return {"memes_added": memes_added, "events_summarized": events_summarized,
            "episodes_summarized": episodes_summarized}
