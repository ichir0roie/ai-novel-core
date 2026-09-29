#!/usr/bin/env python3
"""出来事が人物の信念・立場を大きく動かしたときは、その変化は `Character.text`
へ文章として書き込む(`update_character` を使う)。
"""
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from data_access_logic.event.form import EventCreateForm
from data_access_logic.event.record import EventRecord
from db.schema import Character, Event, EventCharacter, Location


class CommitEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: EventCreateForm):
        self.event = event

    def execute(self, session) -> EventRecord:
        self.check_exists(session, Event, self.event.parent_event_id, "parent_event_id")
        self.check_exists(session, Location, self.event.location_id, "location_id")
        for character_id in self.event.character_ids:
            self.check_exists(session, Character, character_id, "character_ids")

        record = Event(**self.event.column_values(Event))
        record.event_characters = [
            EventCharacter(character_id=character_id) for character_id in self.event.character_ids]
        session.add(record)
        session.flush()
        return EventRecord.model_validate(reloaded(session, record, selectinload(Event.event_characters)))
