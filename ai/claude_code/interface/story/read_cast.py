#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery


class ReadCast(StoryQuery):
    def __init__(self, story_id: int, time=None, count: int = 5, levels: int = 1):
        self.story_id = story_id
        self.time = time
        self.count = count
        self.levels = levels

    def execute(self, session) -> _rows.Cast:
        return _rows.cast(session, self.story_id, self.time, count=self.count, levels=self.levels)
