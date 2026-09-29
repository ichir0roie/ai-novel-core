#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.character import reading as character_reading
from data_access_logic.entrypoint import SessionEntrypoint


class ReadCharacter(SessionEntrypoint):
    def __init__(self, character_id: int, time=None, count: int = 5):
        self.character_id = character_id
        self.time = time
        self.count = count

    def execute(self, session) -> character_reading.CharacterSheet:
        return character_reading.character_sheet(session, self.character_id, until=self.time, count=self.count)
