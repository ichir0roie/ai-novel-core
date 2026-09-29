#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import reading as episode_reading


class ListUnsyncedEpisodes(SessionEntrypoint):
    def __init__(self, story_id: int | None = None):
        self.story_id = story_id

    def execute(self, s: Session) -> list[episode_reading.UnsyncedEpisode]:
        return episode_reading.unsynced_episodes(s, self.story_id)
