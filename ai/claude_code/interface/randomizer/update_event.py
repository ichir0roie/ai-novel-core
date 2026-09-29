#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from data_access_logic.event.form import EventUpdateForm
from data_access_logic.event.record import EventRecord
from db.schema import Event, Location


class UpdateEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: EventUpdateForm):
        self.event = event

    def execute(self, session) -> EventRecord:
        record = self.get_or_raise(session, self.event.id, "出来事")
        if self.event.parent_event_id == self.event.id:
            raise ValueError(f"parent_event_id={self.event.id} が自分自身を指している")
        self.check_exists(session, Event, self.event.parent_event_id, "parent_event_id")
        self.check_exists(session, Location, self.event.location_id, "location_id")

        self.apply(session, record, self.event.changed_column_values(Event))
        return EventRecord.model_validate(reloaded(session, record, selectinload(Event.event_characters)))
