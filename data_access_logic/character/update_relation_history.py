#!/usr/bin/env python3
"""関係の来歴の行を一つ、id で指して直す。渡した欄だけを直し、同じ関係のほかの行には触れない。
行の id は表の API の `character_relation` の行の `histories` の各行の `id` で読む。

    UpdateRelationHistory(history_id=7, history=CharacterRelationHistoryChange(start="1201")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterRelationHistoryChange
from data_access_logic.character.record import CharacterRelationHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import changed_history
from db.schema import CharacterRelationHistory


class UpdateRelationHistory(CommitEntrypoint):
    def __init__(self, history_id: int, history: CharacterRelationHistoryChange):
        self.history_id = history_id
        self.history = history

    def execute(self, s: Session) -> CharacterRelationHistoryRow:
        row = common_query.get_row(s, CharacterRelationHistory, self.history_id)
        changed_history(row, self.history)
        self.finalize(s, row)
        return CharacterRelationHistoryRow.model_validate(row)
