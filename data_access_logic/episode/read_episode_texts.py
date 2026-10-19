#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import reading as episode_reading
from data_access_logic.episode.reading import EpisodeText


class ReadEpisodeTexts(SessionEntrypoint):
    """話を id で読む(作品・題・時刻・プロット・本文)。時刻の順に返す。"""

    def __init__(self, episode_ids: list[int]):
        self.episode_ids = episode_ids

    def execute(self, s: Session) -> list[EpisodeText]:
        return episode_reading.episode_texts(s, self.episode_ids)
