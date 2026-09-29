#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode.record import EpisodeHead
from data_access_logic.story import reading


class ReadEpisodes(SessionEntrypoint):
    def __init__(self, story_id: int, count: int = 10, before=None, text: bool = True):
        self.story_id = story_id
        self.count = count
        self.before = before
        self.text = text

    def execute(self, session) -> list[EpisodeHead]:
        return reading.episodes(session, self.story_id, count=self.count, before=self.before, text=self.text)
