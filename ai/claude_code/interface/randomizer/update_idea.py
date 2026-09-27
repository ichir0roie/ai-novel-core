#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from ai.time_keeper import idea_alias
from db.child_lists import load_children
from db.schema import Idea, Location
from db.schema_pydantic import to_dict


class UpdateIdea(CommitDraft):
    model = Idea

    def __init__(self, idea: str | dict):
        self.idea = idea

    def execute(self, session) -> dict:
        data = self.parse(self.idea)
        idea_id = data.pop("id", None)
        if idea_id is None:
            raise ValueError("id は必須(直す対象のアイデア)")
        notes = data.pop("notes", None)
        self.check_columns(data)

        record = session.get(Idea, idea_id)
        if record is None:
            raise ValueError(f"id={idea_id} というアイデアが見つからない")

        self.check_exists(session, Location, data.get("location_id"), "location_id")
        new_parent_id = data.get("parent_idea_id")
        if new_parent_id == idea_id:
            raise ValueError(f"parent_idea_id={idea_id} が自分自身を指している")
        self.check_exists(session, Idea, new_parent_id, "parent_idea_id")
        if new_parent_id is not None:
            self._check_not_descendant(session, idea_id, new_parent_id)
        idea_alias.check(session, idea_id, data.get("alias_of_idea_id"))

        for key, value in data.items():
            setattr(record, key, value)
        if notes is not None:
            load_children(record, "notes", notes)
        self.finalize(session, record)
        return to_dict(record)

    @staticmethod
    def _check_not_descendant(session, idea_id: int, new_parent_id: int) -> None:
        """new_parent_id が idea_id の下位(子孫)なら、親にすると木が循環するので弾く。"""
        seen: set[int] = set()
        ancestor_id: int | None = new_parent_id
        while ancestor_id is not None and ancestor_id not in seen:
            seen.add(ancestor_id)
            ancestor = session.get(Idea, ancestor_id)
            if ancestor is None or ancestor.parent_idea_id is None:
                return
            if ancestor.parent_idea_id == idea_id:
                raise ValueError(f"parent_idea_id={new_parent_id} は id={idea_id} の下位のアイデアなので、親にすると循環する")
            ancestor_id = ancestor.parent_idea_id
