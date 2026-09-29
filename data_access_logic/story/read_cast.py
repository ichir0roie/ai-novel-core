#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading as story_reading
from db.stamp import Stamp


class ReadCast(SessionEntrypoint):
    def __init__(self, story_id: int, time: Stamp | str | None = None, count: int = 5, levels: int = 1):
        self.story_id = story_id
        self.time = time
        self.count = count
        self.levels = levels

    def execute(self, s: Session) -> story_reading.Cast:
        return story_reading.cast(s, self.story_id, self.time, count=self.count, levels=self.levels)
