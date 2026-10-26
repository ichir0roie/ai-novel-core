#!/usr/bin/env python3
"""展開を一つ、変えた行と食い違いの一覧つきで読む。

    ReadExpansion(expansion_id=12).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint, record_of
from data_access_logic.expansion.record import ExpansionDetail
from data_access_logic.query import common_query
from db.schema import Expansion


class ReadExpansion(SessionEntrypoint):
    def __init__(self, expansion_id: int):
        self.expansion_id = expansion_id

    def execute(self, s: Session) -> ExpansionDetail:
        return record_of(s, ExpansionDetail, common_query.get_row(s, Expansion, self.expansion_id))
