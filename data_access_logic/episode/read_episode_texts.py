#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import reading as episode_reading
from data_access_logic.episode.reading import EpisodeText


class ReadEpisodeTexts(SessionEntrypoint):
    """話を id で読む(作品・題・時刻・プロット・本文・概要)。時刻の順に返す。

    `ReadEpisodeCasting` / `ReadEpisodeBrief` の「関わった話」「前の話の概要」の話idを渡して、本文まで読むのに使う。
    """

    def __init__(self, episode_ids: list[int]):
        self.episode_ids = episode_ids

    def execute(self, s: Session) -> list[EpisodeText]:
        return episode_reading.episode_texts(s, self.episode_ids)
