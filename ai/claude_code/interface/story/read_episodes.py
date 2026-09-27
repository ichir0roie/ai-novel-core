#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery


class ReadEpisodes(StoryQuery):
    def __init__(self, story_id: int, count: int = 10, before=None,
                 text: bool = True):
        self.story_id = story_id
        self.count = count
        self.before = before
        self.text = text

    def execute(self, session) -> list[dict]:
        return _rows.episodes(session, int(self.story_id), count=int(self.count),
                              before=self.before, text=self.text)
