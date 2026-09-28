#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitMemeSource
from ai.time_keeper.idea_context import find_or_create_classification
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
        recognitions = data.pop("recognitions", [])
        self.check_columns(data)
        if not data.get("name"):
            raise ValueError("name は必須")
        if not data.get("kind"):
            raise ValueError("kind は必須")
        data.setdefault("text", "")

        self.check_exists(session, Location, data.get("location_id"), "location_id")
        self.check_exists(session, Idea, data.get("parent_idea_id"), "parent_idea_id")
        # 親を渡されていなければ、kind の分類アイデアを場所から探し、無ければ作って親にする。
        # ただし、いま作っているのがまさにその分類自身(name == kind)なら、自分自身の親を探しに行かない
        if data.get("parent_idea_id") is None and data.get("name") != data.get("kind"):
            classification = find_or_create_classification(session, data["kind"], data.get("location_id"))
            if classification is not None:
                data["parent_idea_id"] = classification.id

        record = Idea(**data)
        load_children(record, "notes", notes)
        load_children(record, "recognitions", recognitions)
        session.add(record)
        self.finalize(session, record)
        return to_dict(record)
