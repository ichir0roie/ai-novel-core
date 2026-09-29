#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.character.form import CharacterRelationCreateForm
from data_access_logic.character.record import CharacterRelationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from db.schema import Character, CharacterRelation


class CommitCharacterRelation(CommitEntrypoint):
    model = CharacterRelation

    def __init__(self, relation: CharacterRelationCreateForm):
        self.relation = relation

    def execute(self, session) -> CharacterRelationRecord:
        self.check_exists(session, Character, self.relation.character_id_1, "character_id_1")
        self.check_exists(session, Character, self.relation.character_id_2, "character_id_2")

        record = CharacterRelation()
        self.relation.write_to(record)
        session.add(record)
        self.finalize(session, record)
        return CharacterRelationRecord.model_validate(record)
