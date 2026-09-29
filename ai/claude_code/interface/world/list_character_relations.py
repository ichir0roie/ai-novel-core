#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.world._base import WorldQuery
from data_access_logic.character.record import CharacterRelationRecord
from data_access_logic.query import common_query


class ListCharacterRelations(WorldQuery):
    def __init__(self, character_id: int | None = None):
        self.character_id = character_id

    def select(self):
        return common_query.character_relations_select(self.character_id)

    def row(self, row) -> CharacterRelationRecord:
        return CharacterRelationRecord.model_validate(row)
