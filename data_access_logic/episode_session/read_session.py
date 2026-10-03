#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_session.record import SessionRecord
from data_access_logic.episode_session.turns import session_select


class ReadSession(SessionEntrypoint):
    """話のセッションの行を、手番の順(id の順)にすべて読む(人物の内心も入る。語り部と本文を書くときに読む)。"""

    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> list[SessionRecord]:
        return [SessionRecord.model_validate(row) for row in s.scalars(session_select(self.episode_id)).all()]
