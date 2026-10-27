#!/usr/bin/env python3
"""人物の来歴の行を一つ、id で指して直す。渡した欄だけを直し、同じ人物のほかの行には触れない。
行の id は `ReadCharacter` などの `histories` の各行の `id` で読む。

    UpdateCharacterHistory(history_id=40, history=CharacterHistoryChange(description="港で疫病に罹り、半月寝込む")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import check_knowers
from data_access_logic.character.form import CharacterHistoryChange
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import changed_history
from db.schema import CharacterHistory


class UpdateCharacterHistory(CommitEntrypoint):
    def __init__(self, history_id: int, history: CharacterHistoryChange):
        self.history_id = history_id
        self.history = history

    def execute(self, s: Session) -> CharacterHistoryRow:
        row = common_query.get_row(s, CharacterHistory, self.history_id)
        check_knowers(s, self.history.knowers)
        changed_history(row, self.history)
        self.finalize(s, row)
        return CharacterHistoryRow.model_validate(row)
