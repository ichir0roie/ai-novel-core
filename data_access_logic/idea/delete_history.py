#!/usr/bin/env python3
"""アイデアの呼び名の行を一つ、id で指して消す。知る相手の行も消える。同じアイデアのほかの行には触れない。消した行を返す。

    DeleteIdeaHistory(history_id=30).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.query import common_query
from db.schema import IdeaHistory


class DeleteIdeaHistory(CommitEntrypoint):
    def __init__(self, history_id: int):
        self.history_id = history_id

    def execute(self, s: Session) -> IdeaHistoryRow:
        row = common_query.get_row(s, IdeaHistory, self.history_id)
        deleted = IdeaHistoryRow.model_validate(row)
        s.delete(row)
        return deleted
