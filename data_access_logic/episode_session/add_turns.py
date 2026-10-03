#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_session.form import EventRequest, TurnRequest
from data_access_logic.episode_session.record import SessionRecord
from db.schema import Character, Episode, EpisodeCharacterSession


class AddTurns(CommitEntrypoint):
    """語り部が、話のセッションに手番の要求の行とイベントの行を並べた順に足す。人物役は自分の行が来たら行動を入れる。"""

    model = EpisodeCharacterSession

    def __init__(self, episode_id: int, turns: list[TurnRequest | EventRequest]):
        self.episode_id = episode_id
        self.turns = turns

    def execute(self, s: Session) -> list[SessionRecord]:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        records = []
        for turn in self.turns:
            if isinstance(turn, TurnRequest):
                self.check_exists(s, Character, turn.character_id, "character_id")
            record = EpisodeCharacterSession(episode_id=self.episode_id, is_event=isinstance(turn, EventRequest))
            turn.write_to(record)
            s.add(record)
            self.finalize(s, record)
            records.append(record_of(s, SessionRecord, record))
        return records
