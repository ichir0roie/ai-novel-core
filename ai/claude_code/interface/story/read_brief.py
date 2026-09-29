#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery


class ReadBrief(StoryQuery):
    def __init__(self, place_id: int, time, reach: int = 60, full: bool = False):
        self.place_id = place_id
        self.time = time
        self.reach = reach
        self.full = full

    def execute(self, session) -> _rows.Brief:
        return _rows.brief(session, self.place_id, self.time, reach=self.reach, full=self.full)
