#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from ai.claude_code.interface.story._base import StoryCommit
from data_access_logic.story.record import DeletedStory
from db.schema import Episode, Story


class DeleteStory(StoryCommit):
    model = Story

    def __init__(self, story_id: int):
        self.story_id = story_id

    def execute(self, session) -> DeletedStory:
        record = self.get_or_raise(session, self.story_id, "作品")

        episode_id = session.scalar(
            select(Episode.id).where(Episode.story_id == record.id).limit(1))
        if episode_id is not None:
            raise ValueError(
                f"story_id={record.id} にはまだ話が残っている。先に話を消してから削除する")

        deleted = DeletedStory.model_validate(record)
        session.delete(record)
        return deleted
