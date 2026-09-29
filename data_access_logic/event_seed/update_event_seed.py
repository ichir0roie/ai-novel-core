#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event_seed.form import EventSeedUpdateForm
from data_access_logic.event_seed.record import EventSeedRecord
from data_access_logic.query import common_query
from db.schema import EventSeed


class UpdateEventSeed(CommitEntrypoint):
    model = EventSeed

    def __init__(self, seed: EventSeedUpdateForm):
        self.seed = seed

    def execute(self, session) -> EventSeedRecord:
        record = common_query.get_row(session, EventSeed, self.seed.id)
        self.seed.write_changes_to(record)
        self.finalize(session, record)
        return EventSeedRecord.model_validate(record)
