#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_session.record import SessionRecord
from data_access_logic.episode_session.turns import author_turn
from db.schema import Episode, EpisodeCharacterSession, SessionKind


class HandOver(CommitEntrypoint):
    """語り部が一巡を終え、作者に番を渡す(行動の空いた作者の行を足す)。作者が書く(`SaveText`・`AddAuthorLine`)まで、
    語り部は本文に書き足せず(`AppendText`)、後に足す手番も待つ。"""


    def __init__(self, episode_id: int, request: str = "作者の番"):
        self.episode_id = episode_id
        self.request = request

    def execute(self, s: Session) -> SessionRecord:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        waiting = author_turn(s, self.episode_id)
        if waiting is not None:
            raise ValueError(f"もう作者の番(id={waiting.id})")
        record = EpisodeCharacterSession(episode_id=self.episode_id, kind=SessionKind.AUTHOR, request=self.request)
        s.add(record)
        self.finalize(s, record)
        return record_of(s, SessionRecord, record)
