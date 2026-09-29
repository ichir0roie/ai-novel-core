#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.ai_entrypoint import CommitAndRefresh
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Location, Story


class CommitStory(CommitAndRefresh):
    model = Story

    def __init__(self, story: StoryCreateForm):
        self.story = story

    def execute(self, s: Session) -> StoryRecord:
        self.check_exists(s, Location, self.story.world_id, "world_id")
        self.check_exists(s, Location, self.story.location_id, "location_id")

        record = Story()
        self.story.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return StoryRecord.model_validate(record)
