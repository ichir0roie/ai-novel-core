#!/usr/bin/env python3
"""スキルの来歴の行を一つ、id で指して直す。渡した欄だけを直し、同じスキルのほかの行には触れない。
行の id は表の API の `character_skill` の行の `histories` の各行の `id` で読む。

    UpdateSkillHistory(history_id=12, history=CharacterSkillHistoryChange(end="1210")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import check_knowers
from data_access_logic.character.form import CharacterSkillHistoryChange
from data_access_logic.character.record import CharacterSkillHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import changed_history
from db.schema import CharacterSkillHistory


class UpdateSkillHistory(CommitEntrypoint):
    def __init__(self, history_id: int, history: CharacterSkillHistoryChange):
        self.history_id = history_id
        self.history = history

    def execute(self, s: Session) -> CharacterSkillHistoryRow:
        row = common_query.get_row(s, CharacterSkillHistory, self.history_id)
        check_knowers(s, self.history.knowers)
        changed_history(row, self.history)
        self.finalize(s, row)
        return CharacterSkillHistoryRow.model_validate(row)
