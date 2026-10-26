#!/usr/bin/env python3
"""場所の来歴の行を一つ足す。今ある行には触れない。知る相手を渡さなければ、その場所(その時刻に住む人物)が知る。

    AppendLocationHistory(location_id=61, history=LocationHistoryRow(start="1200/04/01", description="港で疫病が流行る")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import AppendedRow, appended, check_knowers
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.query import common_query
from db.child_lists import appended_history
from db.schema import Location, LocationHistory


class AppendLocationHistory(CommitEntrypoint):
    def __init__(self, location_id: int, history: LocationHistoryRow):
        self.location_id = location_id
        self.history = history

    def execute(self, s: Session) -> AppendedRow:
        location = common_query.get_row(s, Location, self.location_id)
        check_knowers(s, self.history.knowers)
        row = appended_history(self.history, LocationHistory, owner=location)
        row.location_id = location.id
        s.add(row)
        return appended(s, row)
