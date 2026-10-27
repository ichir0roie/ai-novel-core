#!/usr/bin/env python3
"""関係の来歴の行を一つ、id で指して消す。同じ関係のほかの行には触れない。消した行を返す。

    DeleteRelationHistory(history_id=7).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterRelationHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterRelationHistory


class DeleteRelationHistory(CommitEntrypoint):
    def __init__(self, history_id: int):
        self.history_id = history_id

    def execute(self, s: Session) -> CharacterRelationHistoryRow:
        row = common_query.get_row(s, CharacterRelationHistory, self.history_id)
        deleted = CharacterRelationHistoryRow.model_validate(row)
        s.delete(row)
        return deleted
