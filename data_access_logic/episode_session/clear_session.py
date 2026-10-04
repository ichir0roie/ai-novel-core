#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode_session.record import SessionCleared
from db.schema import Episode, EpisodeCharacterSession


class ClearSession(CommitEntrypoint):
    """話のセッションの行を、その話のぶんすべて消す。終了の行が残ると人物役がすぐ止まるので、手番を演じ直す前に消す。"""


    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> SessionCleared:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        deleted = s.scalars(delete(EpisodeCharacterSession)
                            .where(EpisodeCharacterSession.episode_id == self.episode_id)
                            .returning(EpisodeCharacterSession.id)).all()
        return SessionCleared(episode_id=self.episode_id, deleted=len(deleted))
