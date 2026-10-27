#!/usr/bin/env python3
"""人物の来歴の行を一つ、id で指して消す。知る相手の行も消える。同じ人物のほかの行には触れない。消した行を返す。

    DeleteCharacterHistory(history_id=40).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterHistory


class DeleteCharacterHistory(CommitEntrypoint):
    def __init__(self, history_id: int):
        self.history_id = history_id

    def execute(self, s: Session) -> CharacterHistoryRow:
        row = common_query.get_row(s, CharacterHistory, self.history_id)
        deleted = CharacterHistoryRow.model_validate(row)
        s.delete(row)
        return deleted
