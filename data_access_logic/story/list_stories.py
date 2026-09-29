#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading as story_reading


class ListStories(SessionEntrypoint):
    def execute(self, session) -> list[story_reading.StoryDigest]:
        return story_reading.stories(session)
