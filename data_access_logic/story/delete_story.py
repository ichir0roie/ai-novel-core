#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.record import DeletedStory
from db.schema import Episode, Story


class DeleteStory(CommitEntrypoint):

    def __init__(self, story_id: int):
        self.story_id = story_id

    def execute(self, s: Session) -> DeletedStory:
        record = common_query.get_row(s, Story, self.story_id)

        episode_id = s.scalar(
            select(Episode.id).where(Episode.story_id == record.id).limit(1))
        if episode_id is not None:
            raise ValueError(
                f"story_id={record.id} にはまだ話が残っている。先に話を消してから削除する")
        child_id = s.scalar(
            select(Story.id).where(Story.parent_story_id == record.id).limit(1))
        if child_id is not None:
            raise ValueError(
                f"story_id={record.id} にはまだ子の作品(id={child_id})が残っている。先に子の作品を消すか付け替える")

        deleted = DeletedStory.model_validate(record)
        s.delete(record)
        return deleted
