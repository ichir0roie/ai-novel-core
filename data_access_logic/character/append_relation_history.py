#!/usr/bin/env python3
"""関係の来歴の行を一つ足す。今ある行には触れない。

    AppendRelationHistory(character_relation_id=3, history=CharacterRelationHistoryRow(start="1200", description="港で再会する")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import AppendedRow, appended
from data_access_logic.character.record import CharacterRelationHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterRelation, CharacterRelationHistory


class AppendRelationHistory(CommitEntrypoint):
    def __init__(self, character_relation_id: int, history: CharacterRelationHistoryRow):
        self.character_relation_id = character_relation_id
        self.history = history

    def execute(self, s: Session) -> AppendedRow:
        relation = common_query.get_row(s, CharacterRelation, self.character_relation_id)
        row = CharacterRelationHistory(character_relation_id=relation.id)
        self.history.write_to(row)
        s.add(row)
        return appended(s, row)
