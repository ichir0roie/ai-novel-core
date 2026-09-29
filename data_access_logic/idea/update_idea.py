#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.form import IdeaUpdateForm
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.query import common_query
from db.child_lists import replaced_rows
from db.schema import Idea, IdeaRecognition, Location


class UpdateIdea(CommitEntrypoint):
    model = Idea

    def __init__(self, idea: IdeaUpdateForm):
        self.idea = idea

    def execute(self, session) -> IdeaRecord:
        form = self.idea
        record = common_query.get_row(session, Idea, form.id)

        self.check_exists(session, Location, form.location_id, "location_id")
        if form.parent_idea_id == form.id:
            raise ValueError(f"parent_idea_id={form.id} が自分自身を指している")
        self.check_exists(session, Idea, form.parent_idea_id, "parent_idea_id")
        if form.parent_idea_id is not None:
            self._check_not_descendant(session, form.id, form.parent_idea_id)

        if form.recognitions is not None:
            record.recognitions = replaced_rows(record.recognitions, form.recognitions, IdeaRecognition)
        form.write_changes_to(record)
        self.finalize(session, record)
        return IdeaRecord.model_validate(record)

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
