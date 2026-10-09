#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterRelationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterRelation


class DeleteCharacterRelation(CommitEntrypoint):
    """人物どうしの関係を消す。関係の来歴の行も消える。"""

    def __init__(self, character_relation_id: int):
        self.character_relation_id = character_relation_id

    def execute(self, s: Session) -> CharacterRelationRecord:
        record = common_query.get_row(s, CharacterRelation, self.character_relation_id)
        deleted = CharacterRelationRecord.model_validate(record)
        s.delete(record)
        return deleted
