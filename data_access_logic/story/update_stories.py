#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.form import StoryUpdateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Story


class UpdateStories(CommitEntrypoint):
    """作品をまとめて直す。GUI の作品ツリーの編集モードで溜めた並び・親の付け替えを、一つのトランザクションで書く。"""

    def __init__(self, stories: list[StoryUpdateForm]):
        self.stories = stories

    def execute(self, s: Session) -> list[StoryRecord]:
        records = []
        for story in self.stories:
            record = common_query.get_row(s, Story, story.id)
            self.check_exists(s, Story, story.parent_story_id, "parent_story_id")
            story.write_changes_to(record)
            records.append(record)
        # 親の入れ替え(A の子の B を A の親にするなど)は一つずつ確かめると途中で循環に見えるので、全部書いてから確かめる
        for record in records:
            if record.parent_story_id is not None and record.id in common_query.story_path_ids(s, record.parent_story_id):
                raise ValueError(f"story_id={record.id} を、自分か自分の子孫の作品の子にはできない")
        s.flush()
        return [StoryRecord.model_validate(record) for record in records]
