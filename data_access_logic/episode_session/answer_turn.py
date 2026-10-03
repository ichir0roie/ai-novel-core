#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_session.form import TurnAnswer
from data_access_logic.episode_session.record import SessionRecord
from data_access_logic.episode_session.turns import current_turn
from data_access_logic.query import common_query
from db.schema import EpisodeCharacterSession


class AnswerTurn(CommitEntrypoint):
    """人物役が、自分の番の要求の行に一手(内心・行動・セリフ・狙い)を入れる。"""

    model = EpisodeCharacterSession

    def __init__(self, record_id: int, answer: TurnAnswer):
        self.record_id = record_id
        self.answer = answer

    def execute(self, s: Session) -> SessionRecord:
        record = common_query.get_row(s, EpisodeCharacterSession, self.record_id)
        if record.closing:
            raise ValueError(f"id={record.id} は終了の行。行動は入れない")
        if record.action is not None:
            raise ValueError(f"id={record.id} にはもう行動が入っている")
        current = current_turn(s, record.episode_id)
        if current is None or current.id != record.id:
            raise ValueError(f"id={record.id} はまだ番が来ていない(いまの番は id={current.id if current else None})")
        self.answer.write_to(record)
        self.finalize(s, record)
        return record_of(s, SessionRecord, record)
