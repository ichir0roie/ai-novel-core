#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_comment.record import CommentDiff
from db.schema import EpisodeCommentDiff


class ReadDiffsSince(SessionEntrypoint):
    """本文の差分のうち、`after_diff_id` より新しいものを古い順に読む(語り部・人物役が新しい差分を待つ)。"""

    def __init__(self, episode_id: int, after_diff_id: int = 0):
        self.episode_id = episode_id
        self.after_diff_id = after_diff_id

    def execute(self, s: Session) -> list[CommentDiff]:
        rows = s.scalars(select(EpisodeCommentDiff)
                         .where(EpisodeCommentDiff.episode_id == self.episode_id, EpisodeCommentDiff.id > self.after_diff_id)
                         .order_by(EpisodeCommentDiff.id)).all()
        return [CommentDiff.model_validate(row) for row in rows]
