#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.ai_entrypoint import CommitMemeSource
from data_access_logic.idea.classification import find_or_create_classification
from data_access_logic.idea.form import IdeaCreateForm
from data_access_logic.idea.record import IdeaRecord
from db.child_lists import replaced_rows
from db.schema import Idea, IdeaRecognition, Location


class CommitIdea(CommitMemeSource):
    model = Idea

    def __init__(self, idea: IdeaCreateForm, fact_check: bool = True):
        self.idea = idea
        self.fact_check = fact_check

    def execute(self, s: Session) -> IdeaRecord:
        form = self.idea
        self.check_exists(s, Location, form.location_id, "location_id")
        self.check_exists(s, Idea, form.parent_idea_id, "parent_idea_id")

        record = Idea()
        form.write_to(record)
        # 親を渡されていなければ、kind の分類アイデアを場所から探し、無ければ作って親にする。
        # ただし、いま作っているのがまさにその分類自身(name == kind)なら、自分自身の親を探しに行かない
        if form.parent_idea_id is None and form.name != form.kind:
            classification = find_or_create_classification(s, form.kind, form.location_id)
            if classification is not None:
                record.parent_idea_id = classification.id
        record.recognitions = replaced_rows([], form.recognitions, IdeaRecognition)
        s.add(record)
        self.finalize(s, record)
        return IdeaRecord.model_validate(record)
