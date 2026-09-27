#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story._base import StoryCommit
from db.schema import Episode, Story


class DeleteStory(StoryCommit):
    model = Story

    def __init__(self, story_id: int):
        self.story_id = story_id

    def execute(self, session) -> dict:
        record = session.get(Story, int(self.story_id))
        if record is None:
            raise UnknownRecordError(
                f"story_id={self.story_id} という id の story が見つからない")

        episode_id = session.scalar(
            select(Episode.id).where(Episode.story_id == record.id).limit(1))
        if episode_id is not None:
            raise ValueError(
                f"story_id={record.id} にはまだ話が残っている。先に話を消してから削除する")

        data = {"id": record.id, "name": record.name, "place_id": record.place_id,
                "text": record.text}
        session.delete(record)
        return data
