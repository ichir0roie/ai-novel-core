#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.form import StoryUpdateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Location, Story


class UpdateStory(CommitEntrypoint):
    model = Story

    def __init__(self, story: StoryUpdateForm):
        self.story = story

    def execute(self, session: Session) -> StoryRecord:
        record = common_query.get_row(session, Story, self.story.id)
        self.check_exists(session, Location, self.story.world_id, "world_id")
        self.check_exists(session, Location, self.story.place_id, "place_id")

        self.story.write_changes_to(record)
        self.finalize(session, record)
        return StoryRecord.model_validate(record)
