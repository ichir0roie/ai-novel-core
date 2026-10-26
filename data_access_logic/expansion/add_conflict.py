#!/usr/bin/env python3
"""展開が見つけた、作者の行との食い違いを残す。AI は作者の行を直せないので、直す案を添えて作者の判断を待つ
(`review.list_pending_reviews.ListPendingReviews` に出る)。

    AddConflict(ConflictCreateForm(expansion_id=12, table_name="character", row_id=5,
                                   detail="来歴に一人っ子とあるが、一言では姉がいる", proposal="来歴の行を …")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.expansion.form import ConflictCreateForm
from data_access_logic.expansion.record import ExpansionConflictRecord
from data_access_logic.expansion.rows import user_row
from data_access_logic.query import common_query
from db.schema import Expansion, ExpansionConflict


class AddConflict(CommitEntrypoint):
    def __init__(self, conflict: ConflictCreateForm):
        self.conflict = conflict

    def execute(self, s: Session) -> ExpansionConflictRecord:
        common_query.get_row(s, Expansion, self.conflict.expansion_id)
        user_row(s, self.conflict.table_name, self.conflict.row_id)
        record = ExpansionConflict()
        self.conflict.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return ExpansionConflictRecord.model_validate(record)
