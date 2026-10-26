#!/usr/bin/env python3
"""世界の展開を終える。何を足し・直したかの要約を書き、状態を done(途中で止まったなら failed)にする。

    FinishExpansion(ExpansionFinishForm(id=12, summary="港の疫病の出来事を三件、医師を一人足した")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.expansion.form import ExpansionFinishForm
from data_access_logic.expansion.record import ExpansionRecord
from data_access_logic.query import common_query
from db.schema import Expansion, ExpansionStatus


def finish(s: Session, form: ExpansionFinishForm) -> ExpansionRecord:
    record = common_query.get_row(s, Expansion, form.id)
    if record.status != ExpansionStatus.RUNNING:
        raise ValueError(f"expansion id={record.id} は {record.status} で、もう終わっている")
    record.summary = form.summary
    record.status = form.status
    CommitEntrypoint.finalize(s, record)
    return ExpansionRecord.model_validate(record)


class FinishExpansion(CommitEntrypoint):
    def __init__(self, expansion: ExpansionFinishForm):
        self.expansion = expansion

    def execute(self, s: Session) -> ExpansionRecord:
        return finish(s, self.expansion)
