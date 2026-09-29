#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading as story_reading


class ReadBrief(SessionEntrypoint):
    def __init__(self, place_id: int, time, reach: int = 60, full: bool = False):
        self.place_id = place_id
        self.time = time
        self.reach = reach
        self.full = full

    def execute(self, session) -> story_reading.Brief:
        return story_reading.brief(session, self.place_id, self.time, reach=self.reach, full=self.full)
