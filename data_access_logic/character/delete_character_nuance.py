#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterNuanceRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterNuance


class DeleteCharacterNuance(CommitEntrypoint):
    """癖・思い込みの行を一つ消す。消した行を返す。"""

    def __init__(self, character_nuance_id: int):
        self.character_nuance_id = character_nuance_id

    def execute(self, s: Session) -> CharacterNuanceRecord:
        record = common_query.get_row(s, CharacterNuance, self.character_nuance_id)
        deleted = CharacterNuanceRecord.model_validate(record)
        s.delete(record)
        return deleted
