#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.event_seed.form import EventSeedUpdateForm
from data_access_logic.event_seed.record import EventSeedRecord
from db.schema import EventSeed


class UpdateEventSeed(CommitDraft):
    model = EventSeed

    def __init__(self, seed: EventSeedUpdateForm):
        self.seed = seed

    def execute(self, session) -> EventSeedRecord:
        record = self.get_or_raise(session, self.seed.id, "出来事の種")
        self.seed.write_changes_to(record)
        self.finalize(session, record)
        return EventSeedRecord.model_validate(record)
