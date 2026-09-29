#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterRelationUpdateForm
from data_access_logic.character.record import CharacterRelationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterRelation


class UpdateCharacterRelation(CommitEntrypoint):
    model = CharacterRelation

    def __init__(self, relation: CharacterRelationUpdateForm):
        self.relation = relation

    def execute(self, s: Session) -> CharacterRelationRecord:
        record = common_query.get_row(s, CharacterRelation, self.relation.id)
        self.check_exists(s, Character, self.relation.character_id_1, "character_id_1")
        self.check_exists(s, Character, self.relation.character_id_2, "character_id_2")

        self.relation.write_changes_to(record)
        if record.character_id_1 == record.character_id_2:
            raise ValueError("character_id_1 と character_id_2 は別の人物")
        self.finalize(s, record)
        return CharacterRelationRecord.model_validate(record)
