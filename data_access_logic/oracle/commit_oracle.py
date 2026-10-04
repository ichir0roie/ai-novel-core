#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.flows import commit
from data_access_logic.oracle import steps
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import MemeSourceCommitted, OracleRecord


# 確定のあと(`run()` / `show()`)は、`fact_check` なら確定したものを AI に検めさせ、その節を含む本文からミームを抜き出し、
# 足したミームも検める(`flows/commit.py`)
class CommitOracle(CommitEntrypoint):
    def __init__(self, oracle: OracleCreateForm, fact_check: bool = True):
        self.oracle = oracle
        self.fact_check = fact_check

    def execute(self, s: Session) -> OracleRecord:
        return steps.commit_oracle(s, self.oracle)

    def result(self) -> MemeSourceCommitted:
        return commit.commit_oracle(self.oracle, self.fact_check)
