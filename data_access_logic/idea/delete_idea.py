#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.record import IdeaName
from data_access_logic.query import common_query
from db.schema import Idea


class DeleteIdea(CommitEntrypoint):

    def __init__(self, idea_id: int):
        self.idea_id = idea_id

    def execute(self, s: Session) -> IdeaName:
        record = common_query.get_row(s, Idea, self.idea_id)
        child = s.scalars(
            select(Idea.id).where(Idea.parent_idea_id == record.id)).first()
        if child is not None:
            raise ValueError(f"idea_id={self.idea_id} には下位のアイデアが残っている。先にそちらを消すか繋ぎ直す")

        deleted = IdeaName.model_validate(record)
        s.delete(record)
        return deleted
