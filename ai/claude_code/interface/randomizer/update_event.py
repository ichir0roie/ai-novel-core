#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from db.schema import Event, Location


class UpdateEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: str | dict):
        self.event = event

    def execute(self, session) -> dict:
        data = self.parse(self.event)
        event_id = self.require_id(data, "直す対象の出来事")
        self.check_columns(data)

        record = self.get_or_raise(session, event_id, "出来事")

        if data.get("parent_event_id") == event_id:
            raise ValueError(f"parent_event_id={event_id} が自分自身を指している")
        self.check_exists(session, Event, data.get("parent_event_id"), "parent_event_id")
        self.check_exists(session, Location, data.get("location_id"), "location_id")

        return self.apply(session, record, data)
