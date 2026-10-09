#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode_session.record import SessionCleared
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacterSession


class ClearSession(CommitEntrypoint):
    """話のセッションの行を、その話のぶんすべて消す。終了の行が残ると人物役がすぐ止まるので、手番を演じ直す前に消す。
    `from_record_id` を渡すと、その行から後(その行を含む)だけを消し、その手番から演じ直せるようにする。"""


    def __init__(self, episode_id: int, from_record_id: int | None = None):
        self.episode_id = episode_id
        self.from_record_id = from_record_id

    def execute(self, s: Session) -> SessionCleared:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        statement = delete(EpisodeCharacterSession).where(EpisodeCharacterSession.episode_id == self.episode_id)
        if self.from_record_id is not None:
            if common_query.get_row(s, EpisodeCharacterSession, self.from_record_id).episode_id != self.episode_id:
                raise ValueError(f"id={self.from_record_id} は話 id={self.episode_id} のセッションの行でない")
            statement = statement.where(EpisodeCharacterSession.id >= self.from_record_id)
        deleted = s.scalars(statement.returning(EpisodeCharacterSession.id)).all()
        return SessionCleared(episode_id=self.episode_id, deleted=len(deleted))
