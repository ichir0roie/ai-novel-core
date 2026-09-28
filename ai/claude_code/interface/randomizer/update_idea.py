#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from ai.time_keeper import idea_alias
from db.child_lists import load_children
from db.schema import Idea, Location


class UpdateIdea(CommitDraft):
    model = Idea

    def __init__(self, idea: str | dict):
        self.idea = idea

    def execute(self, session) -> dict:
        data = self.parse(self.idea)
        idea_id = self.require_id(data, "直す対象のアイデア")
        notes = data.pop("notes", None)
        self.check_columns(data)

        record = self.get_or_raise(session, idea_id, "アイデア")

        self.check_exists(session, Location, data.get("location_id"), "location_id")
        new_parent_id = data.get("parent_idea_id")
        if new_parent_id == idea_id:
            raise ValueError(f"parent_idea_id={idea_id} が自分自身を指している")
        self.check_exists(session, Idea, new_parent_id, "parent_idea_id")
        if new_parent_id is not None:
            self._check_not_descendant(session, idea_id, new_parent_id)
        idea_alias.check(session, idea_id, data.get("alias_of_idea_id"))

        if notes is not None:
            load_children(record, "notes", notes)
        return self.apply(session, record, data)

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
