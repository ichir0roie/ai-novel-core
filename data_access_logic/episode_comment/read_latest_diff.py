#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_comment.record import LatestDiff
from db.schema import EpisodeCommentDiff


class ReadLatestDiff(SessionEntrypoint):
    """話の一番新しい差分の id(無ければ 0)。反応を始めるとき、それより後の差分だけを待つのに使う。"""

    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> LatestDiff:
        latest = s.scalar(select(func.max(EpisodeCommentDiff.id)).where(EpisodeCommentDiff.episode_id == self.episode_id))
        return LatestDiff(episode_id=self.episode_id, diff_id=latest or 0)
