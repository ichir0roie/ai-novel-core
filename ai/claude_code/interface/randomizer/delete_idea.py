#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.idea.links import relink
from data_access_logic.idea.record import IdeaName
from db.schema import Idea


class DeleteIdea(CommitDraft):
    model = Idea

    def __init__(self, idea_id: int):
        self.idea_id = idea_id

    def execute(self, session) -> IdeaName:
        record = self.get_or_raise(session, self.idea_id, "アイデア")
        child = session.scalars(
            select(Idea.id).where(Idea.parent_idea_id == record.id)).first()
        if child is not None:
            raise ValueError(f"idea_id={self.idea_id} には下位のアイデアが残っている。先にそちらを消すか繋ぎ直す")

        deleted = IdeaName.model_validate(record)
        relink(session, record.id, None)
        session.delete(record)
        return deleted
