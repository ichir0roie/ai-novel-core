#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_comment.record import CommentDiff
from db.schema import Episode, EpisodeCommentDiff


class CloseComment(CommitEntrypoint):
    """書き終えた合図の行を差分の表に足す。反応している語り部と人物役は、それを読んで止まる。"""

    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> CommentDiff:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        record = EpisodeCommentDiff(episode_id=self.episode_id, diff_text="", closing=True)
        s.add(record)
        self.finalize(s, record)
        return record_of(s, CommentDiff, record)
