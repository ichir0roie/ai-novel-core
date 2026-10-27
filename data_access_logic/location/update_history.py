#!/usr/bin/env python3
"""場所の来歴の行を一つ、id で指して直す。渡した欄だけを直し、同じ場所のほかの行には触れない。
行の id は表の API の `location` の行の `histories` の各行の `id` で読む。

    UpdateLocationHistory(history_id=21, history=LocationHistoryChange(description="港で疫病が流行り、桟橋が閉じる")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import check_knowers
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.form import LocationHistoryChange
from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.query import common_query
from db.child_lists import changed_history
from db.schema import LocationHistory


class UpdateLocationHistory(CommitEntrypoint):
    def __init__(self, history_id: int, history: LocationHistoryChange):
        self.history_id = history_id
        self.history = history

    def execute(self, s: Session) -> LocationHistoryRow:
        row = common_query.get_row(s, LocationHistory, self.history_id)
        check_knowers(s, self.history.knowers)
        changed_history(row, self.history)
        self.finalize(s, row)
        return LocationHistoryRow.model_validate(row)
