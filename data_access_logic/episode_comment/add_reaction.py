#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_comment.form import ReactionForm
from data_access_logic.episode_comment.record import ReactionRecord
from data_access_logic.query import common_query
from db.schema import Character, EpisodeCommentDiff, EpisodeCommentReaction


class AddReaction(CommitEntrypoint):
    """語り部・人物役が、本文の差分を読んだ反応(感想・同意・反対・修正案)を足す。"""

    def __init__(self, reaction: ReactionForm):
        self.reaction = reaction

    def execute(self, s: Session) -> ReactionRecord:
        diff = common_query.get_row(s, EpisodeCommentDiff, self.reaction.diff_id)
        self.check_exists(s, Character, self.reaction.character_id, "character_id")
        record = EpisodeCommentReaction(episode_id=diff.episode_id)
        self.reaction.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return record_of(s, ReactionRecord, record)
