#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.form import StoryUpdateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Story


class UpdateStory(CommitEntrypoint):

    def __init__(self, story: StoryUpdateForm):
        self.story = story

    def execute(self, s: Session) -> StoryRecord:
        record = common_query.get_row(s, Story, self.story.id)
        self.check_exists(s, Story, self.story.parent_story_id, "parent_story_id")
        self.story.write_changes_to(record)
        self.finalize(s, record)
        return StoryRecord.model_validate(record)

    def verify(self, s: Session) -> None:
        # 親の入れ替え(A の子の B を A の親にするなど)は、バッチで全部書いてから確かめる
        record = common_query.get_row(s, Story, self.story.id)
        if record.parent_story_id is not None and record.id in common_query.story_path_ids(s, record.parent_story_id):
            raise ValueError(f"story_id={record.id} を、自分か自分の子孫の作品の子にはできない")
