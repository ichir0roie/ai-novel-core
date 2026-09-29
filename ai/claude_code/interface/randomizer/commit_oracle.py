#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitMemeSource
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import OracleRecord
from db.schema import Oracle


class CommitOracle(CommitMemeSource):
    model = Oracle

    def __init__(self, oracle: OracleCreateForm, fact_check: bool = True):
        self.oracle = oracle
        self.fact_check = fact_check

    def execute(self, session) -> OracleRecord:
        record = Oracle()
        self.oracle.write_to(record)
        session.add(record)
        self.finalize(session, record)
        return OracleRecord.model_validate(record)
