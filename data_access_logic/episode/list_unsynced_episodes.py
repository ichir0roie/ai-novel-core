#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story import reading


class ListUnsyncedEpisodes(SessionEntrypoint):
    def __init__(self, story_id: int | None = None):
        self.story_id = story_id

    def execute(self, session) -> list[reading.UnsyncedEpisode]:
        return reading.unsynced_episodes(session, self.story_id)
