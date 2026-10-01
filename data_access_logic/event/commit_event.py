#!/usr/bin/env python3
"""出来事が人物の信念・立場を大きく動かしたときは、その変化は人物の `histories` に、
出来事の時刻から始まる行として書き足す(`update_character` を使う)。
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

    def execute(self, s: Session) -> EventRecord:
        self.check_exists(s, Event, self.event.parent_event_id, "parent_event_id")
        self.check_exists(s, Location, self.event.location_id, "location_id")
        for character_id in self.event.character_ids:
            self.check_exists(s, Character, character_id, "character_ids")

        record = Event()
        self.event.write_to(record)
        record.event_characters = [
            EventCharacter(character_id=character_id) for character_id in self.event.character_ids]
        s.add(record)
        s.flush()
        return record_of(s, EventRecord, record)

    def follow_up(self, s: Session) -> None:
        # 足した出来事自身の本文も種の元になる
        refresh_and_consolidate(s, ai_client)
