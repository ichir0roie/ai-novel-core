#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.record import DeletedStory
from db.schema import Episode, Story


class DeleteStory(CommitEntrypoint):
    model = Story

    def __init__(self, story_id: int):
        self.story_id = story_id

    def execute(self, session) -> DeletedStory:
        record = common_query.get_row(session, Story, self.story_id)

        episode_id = session.scalar(
            select(Episode.id).where(Episode.story_id == record.id).limit(1))
        if episode_id is not None:
            raise ValueError(
                f"story_id={record.id} にはまだ話が残っている。先に話を消してから削除する")

        deleted = DeletedStory.model_validate(record)
        session.delete(record)
        return deleted
