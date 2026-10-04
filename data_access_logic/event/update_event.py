#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event import steps
from data_access_logic.event.form import EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.flows import commit


# 確定のあと(`run()` / `show()`)は、ミームの抜き出しと要約を AI で追いかける(`flows/commit.py`)
class UpdateEvent(CommitEntrypoint):
    def __init__(self, event: EventUpdateForm):
        self.event = event

    def execute(self, s: Session) -> EventRecord:
        return steps.update_event(s, self.event)

    def result(self) -> EventRecord:
        return commit.update_event(self.event)
