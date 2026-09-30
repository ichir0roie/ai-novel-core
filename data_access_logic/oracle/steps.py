#!/usr/bin/env python3
"""oracle の db の段(`data_access_logic/step.py`)。web のセッション(`web_session/`)が API 越しに呼ぶ。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.oracle.commit_oracle import CommitOracle
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.step import RowId, db_step
from db.schema import Oracle


@db_step
def commit_oracle(s: Session, form: OracleCreateForm) -> OracleRecord:
    return CommitOracle(form).execute(s)


@db_step
def oracle_record(s: Session, form: RowId) -> OracleRecord:
    return OracleRecord.model_validate(s.get_one(Oracle, form.id))
