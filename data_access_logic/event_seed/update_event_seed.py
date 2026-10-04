#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event_seed.form import EventSeedUpdateForm
from data_access_logic.event_seed.record import EventSeedRecord
from data_access_logic.query import common_query
from db.schema import EventSeed


class UpdateEventSeed(CommitEntrypoint):

    def __init__(self, seed: EventSeedUpdateForm):
        self.seed = seed

    def execute(self, s: Session) -> EventSeedRecord:
        record = common_query.get_row(s, EventSeed, self.seed.id)
        self.seed.write_changes_to(record)
        self.finalize(s, record)
        return EventSeedRecord.model_validate(record)
