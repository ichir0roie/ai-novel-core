#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import reading as episode_reading
from data_access_logic.episode.record import EpisodeHead
from db.stamp import Stamp


class ReadEpisodes(SessionEntrypoint):
    def __init__(self, story_id: int, count: int = 10, before: Stamp | str | None = None, text: bool = True):
        self.story_id = story_id
        self.count = count
        self.before = before
        self.text = text

    def execute(self, s: Session) -> list[EpisodeHead]:
        return episode_reading.episodes(s, self.story_id, count=self.count, before=self.before, text=self.text)
