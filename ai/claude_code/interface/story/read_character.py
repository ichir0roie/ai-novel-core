#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery


class ReadCharacter(StoryQuery):
    def __init__(self, character_id: int, time=None, count: int = 5):
        self.character_id = character_id
        self.time = time
        self.count = count

    def execute(self, session) -> _rows.CharacterSheet:
        return _rows.character_sheet(session, self.character_id, until=self.time, count=self.count)
