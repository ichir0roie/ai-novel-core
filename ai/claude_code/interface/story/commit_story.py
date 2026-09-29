#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Location, Story


class CommitStory(CommitAndRefresh):
    model = Story

    def __init__(self, story: StoryCreateForm):
        self.story = story

    def execute(self, session) -> StoryRecord:
        self.check_exists(session, Location, self.story.world_id, "world_id")
        self.check_exists(session, Location, self.story.place_id, "place_id")

        record = Story(**self.story.column_values(Story))
        session.add(record)
        self.finalize(session, record)
        return StoryRecord.model_validate(record)
