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
        self.check_exists(s, Character, self.relation.character_1_id, "character_1_id")
        self.check_exists(s, Character, self.relation.character_2_id, "character_2_id")

        self.relation.write_changes_to(record)
        if record.character_1_id == record.character_2_id:
            raise ValueError("character_1_id と character_2_id は別の人物")
        self.finalize(s, record)
        return CharacterRelationRecord.model_validate(record)
