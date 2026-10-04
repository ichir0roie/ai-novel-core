#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.oracle.form import OracleUpdateForm
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.query import common_query
from db.schema import Oracle


class UpdateOracle(CommitEntrypoint):

    def __init__(self, oracle: OracleUpdateForm):
        self.oracle = oracle

    def execute(self, s: Session) -> OracleRecord:
        record = common_query.get_row(s, Oracle, self.oracle.id)
        self.oracle.write_changes_to(record)
        self.finalize(s, record)
        return OracleRecord.model_validate(record)
