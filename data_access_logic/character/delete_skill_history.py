#!/usr/bin/env python3
"""スキルの来歴の行を一つ、id で指して消す。知る相手の行も消える。同じスキルのほかの行には触れない。消した行を返す。

    DeleteSkillHistory(history_id=12).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterSkillHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterSkillHistory


class DeleteSkillHistory(CommitEntrypoint):
    def __init__(self, history_id: int):
        self.history_id = history_id

    def execute(self, s: Session) -> CharacterSkillHistoryRow:
        row = common_query.get_row(s, CharacterSkillHistory, self.history_id)
        deleted = CharacterSkillHistoryRow.model_validate(row)
        s.delete(row)
        return deleted
