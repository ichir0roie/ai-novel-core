#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from data_access_logic.event.form import EventUpdateForm
from data_access_logic.event.record import EventRecord
from db.schema import Character, Event, EventCharacter, Location


class UpdateEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: EventUpdateForm):
        self.event = event

    def execute(self, session) -> EventRecord:
        form = self.event
        record = reloaded(session, self.get_or_raise(session, form.id, "出来事"), selectinload(Event.event_characters))
        if form.parent_event_id == form.id:
            raise ValueError(f"parent_event_id={form.id} が自分自身を指している")
        self.check_exists(session, Event, form.parent_event_id, "parent_event_id")
        self.check_exists(session, Location, form.location_id, "location_id")
        for character_id in form.character_ids or []:
            self.check_exists(session, Character, character_id, "character_ids")

        form.write_changes_to(record)
        if form.character_ids is not None:
            record.event_characters = [EventCharacter(character_id=character_id) for character_id in form.character_ids]
        self.finalize(session, record)
        return EventRecord.model_validate(reloaded(session, record, selectinload(Event.event_characters)))
