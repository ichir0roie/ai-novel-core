#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading as story_reading
from db.stamp import Stamp


class ReadBrief(SessionEntrypoint):
    def __init__(self, place_id: int, time: Stamp | str | None, reach: int = 60, full: bool = False):
        self.place_id = place_id
        self.time = time
        self.reach = reach
        self.full = full

    def execute(self, session: Session) -> story_reading.Brief:
        return story_reading.brief(session, self.place_id, self.time, reach=self.reach, full=self.full)
