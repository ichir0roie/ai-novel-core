#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from data_access_logic.ai_entrypoint import CommitAndRefresh
from data_access_logic.entrypoint import record_of, reloaded
from data_access_logic.event.form import EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.query import common_query
from db.schema import Character, Event, EventCharacter, Location


class UpdateEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: EventUpdateForm):
        self.event = event

    def execute(self, s: Session) -> EventRecord:
        form = self.event
        record = reloaded(s, common_query.get_row(s, Event, form.id), selectinload(Event.event_characters))
        if form.parent_event_id == form.id:
            raise ValueError(f"parent_event_id={form.id} が自分自身を指している")
        self.check_exists(s, Event, form.parent_event_id, "parent_event_id")
        self.check_exists(s, Location, form.location_id, "location_id")
        for character_id in form.character_ids or []:
            self.check_exists(s, Character, character_id, "character_ids")

        form.write_changes_to(record)
        if form.character_ids is not None:
            record.event_characters = [EventCharacter(character_id=character_id) for character_id in form.character_ids]
        self.finalize(s, record)
        return record_of(s, EventRecord, record)
