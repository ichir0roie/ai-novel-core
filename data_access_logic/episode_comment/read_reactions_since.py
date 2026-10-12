#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint, loading
from data_access_logic.episode_comment.record import ReactionRecord
from db.schema import EpisodeCommentReaction


class ReadReactionsSince(SessionEntrypoint):
    """反応のうち、`after_reaction_id` より新しいものを届いた順に読む(画面が見張って増分を足す)。"""

    def __init__(self, episode_id: int, after_reaction_id: int = 0):
        self.episode_id = episode_id
        self.after_reaction_id = after_reaction_id

    def execute(self, s: Session) -> list[ReactionRecord]:
        statement = (select(EpisodeCommentReaction)
                     .where(EpisodeCommentReaction.episode_id == self.episode_id,
                            EpisodeCommentReaction.id > self.after_reaction_id)
                     .order_by(EpisodeCommentReaction.id))
        return [ReactionRecord.model_validate(row) for row in s.scalars(loading(statement, ReactionRecord)).all()]
