#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterRelationCreateForm
from data_access_logic.character.record import CharacterRelationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from db.child_lists import replaced_rows
from db.schema import Character, CharacterRelation, CharacterRelationHistory


class CommitCharacterRelation(CommitEntrypoint):

    def __init__(self, relation: CharacterRelationCreateForm):
        self.relation = relation

    def execute(self, s: Session) -> CharacterRelationRecord:
        self.check_exists(s, Character, self.relation.character_1_id, "character_1_id")
        self.check_exists(s, Character, self.relation.character_2_id, "character_2_id")

        record = CharacterRelation()
        self.relation.write_to(record)
        record.histories = replaced_rows([], self.relation.histories, CharacterRelationHistory)
        s.add(record)
        self.finalize(s, record)
        return CharacterRelationRecord.model_validate(record)
