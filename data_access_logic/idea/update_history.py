#!/usr/bin/env python3
"""アイデアの呼び名の行を一つ、id で指して直す。渡した欄だけを直し、同じアイデアのほかの行には触れない。
行の id は表の API の `idea` の行の `histories` の各行の `id` で読む。

    UpdateIdeaHistory(history_id=30, history=IdeaHistoryChange(detail="港の者は潮風が運ぶ病だと思っている")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import check_knowers
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.form import IdeaHistoryChange
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.query import common_query
from db.child_lists import changed_history
from db.schema import IdeaHistory, Location


class UpdateIdeaHistory(CommitEntrypoint):
    def __init__(self, history_id: int, history: IdeaHistoryChange):
        self.history_id = history_id
        self.history = history

    def execute(self, s: Session) -> IdeaHistoryRow:
        row = common_query.get_row(s, IdeaHistory, self.history_id)
        self.check_exists(s, Location, self.history.location_id, "location_id")
        check_knowers(s, self.history.knowers)
        changed_history(row, self.history)
        self.finalize(s, row)
        return IdeaHistoryRow.model_validate(row)
