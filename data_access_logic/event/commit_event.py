#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event import steps
from data_access_logic.event.form import EventCreateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.flows import commit


# 確定のあと(`run()` / `show()`)は、ミームの抜き出し・要約・出来事の種を AI で追いかける(`flows/commit.py`)
class CommitEvent(CommitEntrypoint):
    def __init__(self, event: EventCreateForm):
        self.event = event

    def execute(self, s: Session) -> EventRecord:
        return steps.commit_event(s, self.event)

    def result(self) -> EventRecord:
        return commit.commit_event(self.event)
