#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import Oracle


class UpdateOracle(CommitDraft):
    model = Oracle

    def __init__(self, oracle: str | dict):
        self.oracle = oracle

    def execute(self, session) -> dict:
        data = self.parse(self.oracle)
        oracle_id = self.require_id(data, "直す対象の oracle")
        self.check_columns(data)
        if "text" in data and not data["text"]:
            raise ValueError("text を空にはできない")

        record = self.get_or_raise(session, oracle_id, "oracle")

        return self.apply(session, record, data)
