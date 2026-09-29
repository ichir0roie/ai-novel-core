#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.character.form import CharacterRelationUpdateForm
from data_access_logic.character.record import CharacterRelationRecord
from db.schema import Character, CharacterRelation


class UpdateCharacterRelation(CommitDraft):
    model = CharacterRelation

    def __init__(self, relation: CharacterRelationUpdateForm):
        self.relation = relation

    def execute(self, session) -> CharacterRelationRecord:
        record = self.get_or_raise(session, self.relation.id, "人物の相関")
        self.check_exists(session, Character, self.relation.character_id_1, "character_id_1")
        self.check_exists(session, Character, self.relation.character_id_2, "character_id_2")

        for key, value in self.relation.changed_column_values(CharacterRelation).items():
            setattr(record, key, value)
        if record.character_id_1 == record.character_id_2:
            raise ValueError("character_id_1 と character_id_2 は別の人物")
        self.finalize(session, record)
        return CharacterRelationRecord.model_validate(record)
