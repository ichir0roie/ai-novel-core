#!/usr/bin/env python3
"""アイデアの呼び名の行を一つ足す。今ある行には触れない。知る相手を渡さなければ、作中のだれも知らない行になる。

    AppendIdeaHistory(idea_id=12, history=IdeaHistoryRow(location_id=61, start="1200", name="港熱",
                                                          detail="港の者は潮風が運ぶ病だと思っている")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import AppendedRow, appended, check_knowers
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.query import common_query
from db.child_lists import appended_history
from db.schema import Idea, IdeaHistory, Location


class AppendIdeaHistory(CommitEntrypoint):
    def __init__(self, idea_id: int, history: IdeaHistoryRow):
        self.idea_id = idea_id
        self.history = history

    def execute(self, s: Session) -> AppendedRow:
        idea = common_query.get_row(s, Idea, self.idea_id)
        self.check_exists(s, Location, self.history.location_id, "location_id")
        check_knowers(s, self.history.knowers)
        row = appended_history(self.history, IdeaHistory)
        row.idea_id = idea.id
        s.add(row)
        return appended(s, row)
