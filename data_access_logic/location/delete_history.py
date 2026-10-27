#!/usr/bin/env python3
"""場所の来歴の行を一つ、id で指して消す。知る相手の行も消える。同じ場所のほかの行には触れない。消した行を返す。

    DeleteLocationHistory(history_id=21).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.query import common_query
from db.schema import LocationHistory


class DeleteLocationHistory(CommitEntrypoint):
    def __init__(self, history_id: int):
        self.history_id = history_id

    def execute(self, s: Session) -> LocationHistoryRow:
        row = common_query.get_row(s, LocationHistory, self.history_id)
        deleted = LocationHistoryRow.model_validate(row)
        s.delete(row)
        return deleted
