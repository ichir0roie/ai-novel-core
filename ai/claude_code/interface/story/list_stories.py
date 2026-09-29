#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery


class ListStories(StoryQuery):
    def execute(self, session) -> list[_rows.StoryDigest]:
        return _rows.stories(session)
