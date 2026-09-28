#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import EventSeed


class UpdateEventSeed(CommitDraft):
    model = EventSeed

    def __init__(self, seed: str | dict):
        self.seed = seed

    def execute(self, session) -> dict:
        data = self.parse(self.seed)
        seed_id = self.require_id(data, "直す対象の出来事の種")
        self.check_columns(data)

        record = self.get_or_raise(session, seed_id, "出来事の種")

        return self.apply(session, record, data)
