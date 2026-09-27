#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery


class ListUnsyncedEpisodes(StoryQuery):
    def __init__(self, story_id: int | None = None):
        self.story_id = story_id

    def execute(self, session) -> list[dict]:
        return _rows.unsynced_episodes(
            session, None if self.story_id is None else int(self.story_id))
