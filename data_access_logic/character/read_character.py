#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character import reading as character_reading
from data_access_logic.entrypoint import SessionEntrypoint
from db.stamp import Stamp


class ReadCharacter(SessionEntrypoint):
    def __init__(self, character_id: int, time: Stamp | str | None = None, count: int = 5):
        self.character_id = character_id
        self.time = time
        self.count = count

    def execute(self, s: Session) -> character_reading.CharacterSheet:
        return character_reading.character_sheet(s, self.character_id, until=self.time, count=self.count)
