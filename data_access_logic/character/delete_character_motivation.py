#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterMotivationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterMotivation


class DeleteCharacterMotivation(CommitEntrypoint):
    """モチベーションの行を一つ消す。消した行を返す。"""

    def __init__(self, character_motivation_id: int):
        self.character_motivation_id = character_motivation_id

    def execute(self, s: Session) -> CharacterMotivationRecord:
        record = common_query.get_row(s, CharacterMotivation, self.character_motivation_id)
        deleted = CharacterMotivationRecord.model_validate(record)
        s.delete(record)
        return deleted
