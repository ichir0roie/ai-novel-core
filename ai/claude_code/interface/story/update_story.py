#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story._base import StoryCommit
from data_access_logic.story.form import StoryUpdateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Location, Story


class UpdateStory(StoryCommit):
    model = Story

    def __init__(self, story: StoryUpdateForm):
        self.story = story

    def execute(self, session) -> StoryRecord:
        record = self.get_or_raise(session, self.story.id, "作品")
        self.check_exists(session, Location, self.story.world_id, "world_id")
        self.check_exists(session, Location, self.story.place_id, "place_id")

        self.apply(session, record, self.story.changed_column_values(Story))
        return StoryRecord.model_validate(record)
