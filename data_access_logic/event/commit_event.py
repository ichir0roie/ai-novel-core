#!/usr/bin/env python3
"""出来事が人物の信念・立場を大きく動かしたときは、その変化は `Character.text`
へ文章として書き込む(`update_character` を使う)。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_entrypoint import CommitAndRefresh
from data_access_logic.entrypoint import record_of
from data_access_logic.event.form import EventCreateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.event_seed.extractor import refresh_and_consolidate
from db.schema import Character, Event, EventCharacter, Location


class CommitEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: EventCreateForm):
        self.event = event

    def execute(self, session: Session) -> EventRecord:
        self.check_exists(session, Event, self.event.parent_event_id, "parent_event_id")
        self.check_exists(session, Location, self.event.location_id, "location_id")
        for character_id in self.event.character_ids:
            self.check_exists(session, Character, character_id, "character_ids")

        record = Event()
        self.event.write_to(record)
        record.event_characters = [
            EventCharacter(character_id=character_id) for character_id in self.event.character_ids]
        session.add(record)
        session.flush()
        return record_of(session, EventRecord, record)

    def follow_up(self, session: Session) -> None:
        # 足した出来事自身の本文も種の元になる
        refresh_and_consolidate(session, ai_client)
