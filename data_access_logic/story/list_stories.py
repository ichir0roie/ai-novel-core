#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading as story_reading


class ListStories(SessionEntrypoint):
    def execute(self, s: Session) -> list[story_reading.StoryDigest]:
        return story_reading.stories(s)
