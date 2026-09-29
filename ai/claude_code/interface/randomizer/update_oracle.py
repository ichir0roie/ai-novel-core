#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.oracle.form import OracleUpdateForm
from data_access_logic.oracle.record import OracleRecord
from db.schema import Oracle


class UpdateOracle(CommitDraft):
    model = Oracle

    def __init__(self, oracle: OracleUpdateForm):
        self.oracle = oracle

    def execute(self, session) -> OracleRecord:
        record = self.get_or_raise(session, self.oracle.id, "oracle")
        self.oracle.write_changes_to(record)
        self.finalize(session, record)
        return OracleRecord.model_validate(record)
