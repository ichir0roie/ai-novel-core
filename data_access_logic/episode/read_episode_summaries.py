#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import reading as episode_reading
from data_access_logic.episode.models import AppearedEpisode


class ReadEpisodeSummaries(SessionEntrypoint):
    """話を id で、概要だけ読む(作品・題・時刻・概要。本文・プロットは返さない)。時刻の順に返す。
    概要は作り直さず、そのときのまま返す(まだ無ければ null)。本文まで要るときだけ `ReadEpisodeTexts` を使う。
    """

    def __init__(self, episode_ids: list[int]):
        self.episode_ids = episode_ids

    def execute(self, s: Session) -> list[AppearedEpisode]:
        return episode_reading.episode_summaries(s, self.episode_ids)
