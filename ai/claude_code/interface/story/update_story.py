#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story._base import StoryCommit
from db.schema import Location, Story


class UpdateStory(StoryCommit):
    model = Story

    def __init__(self, story: str | dict):
        self.story = story

    def execute(self, session) -> dict:
        data = self.parse(self.story)
        story_id = self.require_id(data, "直す対象の作品")
        self.check_columns(data)

        record = self.get_or_raise(session, story_id, "作品")

        self.check_exists(session, Location, data.get("world_id"), "world_id")
        self.check_exists(session, Location, data.get("place_id"), "place_id")

        return self.apply(session, record, data)
