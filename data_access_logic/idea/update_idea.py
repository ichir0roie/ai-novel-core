#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.form import IdeaUpdateForm
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.query import common_query
from db.child_lists import replaced_histories
from db.schema import Idea, IdeaHistory


class UpdateIdea(CommitEntrypoint):

    def __init__(self, idea: IdeaUpdateForm):
        self.idea = idea

    def execute(self, s: Session) -> IdeaRecord:
        form = self.idea
        self.check_knowers(s, form)
        record = common_query.get_row(s, Idea, form.id)

        if form.parent_idea_id == form.id:
            raise ValueError(f"parent_idea_id={form.id} が自分自身を指している")
        self.check_exists(s, Idea, form.parent_idea_id, "parent_idea_id")
        if form.parent_idea_id is not None:
            self._check_not_descendant(s, form.id, form.parent_idea_id)

        if form.histories is not None:
            record.histories = replaced_histories(record.histories, form.histories, IdeaHistory)
        form.write_changes_to(record)
        self.finalize(s, record)
        return IdeaRecord.model_validate(record)

    @staticmethod
    def _check_not_descendant(s: Session, idea_id: int, new_parent_id: int) -> None:
        """new_parent_id が idea_id の下位(子孫)なら、親にすると木が循環するので弾く。"""
        seen: set[int] = set()
        ancestor_id: int | None = new_parent_id
        while ancestor_id is not None and ancestor_id not in seen:
            seen.add(ancestor_id)
            ancestor = s.get(Idea, ancestor_id)
            if ancestor is None or ancestor.parent_idea_id is None:
                return
            if ancestor.parent_idea_id == idea_id:
                raise ValueError(f"parent_idea_id={new_parent_id} は id={idea_id} の下位のアイデアなので、親にすると循環する")
            ancestor_id = ancestor.parent_idea_id
