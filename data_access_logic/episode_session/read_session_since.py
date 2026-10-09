#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_session.record import SessionRecord, SessionSince
from data_access_logic.episode_session.turns import session_select
from db.schema import EpisodeCharacterSession


class ReadSessionSince(SessionEntrypoint):
    """話のセッションの行のうち、`after_record_id` より新しい id の行を手番の順に読む(GUI がセッションを見張って増分を引く)。"""

    def __init__(self, episode_id: int, after_record_id: int | None = None):
        self.episode_id = episode_id
        self.after_record_id = after_record_id

    def execute(self, s: Session) -> SessionSince:
        statement = session_select(self.episode_id)
        if self.after_record_id is not None:
            statement = statement.where(EpisodeCharacterSession.id > self.after_record_id)
        count = s.scalar(select(func.count(EpisodeCharacterSession.id)).where(EpisodeCharacterSession.episode_id == self.episode_id))
        return SessionSince(records=[SessionRecord.model_validate(row) for row in s.scalars(statement).all()],
                            count=count or 0)
