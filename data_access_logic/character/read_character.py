#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading


class ReadCharacter(SessionEntrypoint):
    def __init__(self, character_id: int, time=None, count: int = 5):
        self.character_id = character_id
        self.time = time
        self.count = count

    def execute(self, session) -> reading.CharacterSheet:
        return reading.character_sheet(session, self.character_id, until=self.time, count=self.count)
