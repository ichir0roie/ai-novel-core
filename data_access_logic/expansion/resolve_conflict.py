#!/usr/bin/env python3
"""作者が食い違いを受けた(accepted)か、捨てた(dismissed)かを書く。受けたときに作者の行を直すのは、
作者の手(書き手 user)で、その行の入口を別に呼ぶ。

    ResolveConflict(ConflictResolveForm(id=4, status="accepted")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.expansion.form import ConflictResolveForm
from data_access_logic.expansion.record import ExpansionConflictRecord
from data_access_logic.query import common_query
from db.schema import ConflictStatus, ExpansionConflict


class ResolveConflict(CommitEntrypoint):
    def __init__(self, conflict: ConflictResolveForm):
        self.conflict = conflict

    def execute(self, s: Session) -> ExpansionConflictRecord:
        record = common_query.get_row(s, ExpansionConflict, self.conflict.id)
        if record.status != ConflictStatus.OPEN:
            raise ValueError(f"expansion_conflict id={record.id} は {record.status} で、もう決まっている")
        record.status = self.conflict.status
        self.finalize(s, record)
        return ExpansionConflictRecord.model_validate(record)
