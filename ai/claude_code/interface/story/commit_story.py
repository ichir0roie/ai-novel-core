#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from db.schema import Location, Story
from db.schema_pydantic import to_dict


class CommitStory(CommitAndRefresh):
    model = Story

    def __init__(self, story: str | dict):
        self.story = story

    def execute(self, session) -> dict:
        data = self.parse(self.story)
        data.pop("id", None)
        self.check_columns(data)
        if not data.get("name"):
            raise ValueError("name は必須")
        data.setdefault("text", "")
        data.setdefault("narration", "")
        data.setdefault("state", "")

        self.check_exists(session, Location, data.get("world_id"), "world_id")
        self.check_exists(session, Location, data.get("place_id"), "place_id")

        record = Story(**data)
        session.add(record)
        self.finalize(session, record)
        return to_dict(record)
