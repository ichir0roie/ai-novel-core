#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitMemeSource
from ai.time_keeper import idea_alias
from db.child_lists import load_children
from db.schema import Idea, Location
from db.schema_pydantic import to_dict


class CommitIdea(CommitMemeSource):
    model = Idea

    def __init__(self, idea: str | dict, fact_check: bool = True):
        self.idea = idea
        self.fact_check = fact_check

    def execute(self, session) -> dict:
        data = self.parse(self.idea)
        data.pop("id", None)
        notes = data.pop("notes", [])
        self.check_columns(data)
        if not data.get("name"):
            raise ValueError("name は必須")
        if not data.get("kind"):
            raise ValueError("kind は必須")
        data.setdefault("text", "")

        self.check_exists(session, Location, data.get("location_id"), "location_id")
        self.check_exists(session, Idea, data.get("parent_idea_id"), "parent_idea_id")
        idea_alias.check(session, None, data.get("alias_of_idea_id"))

        record = Idea(**data)
        load_children(record, "notes", notes)
        session.add(record)
        self.finalize(session, record)
        return to_dict(record)
