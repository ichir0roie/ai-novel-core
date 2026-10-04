#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.classification import find_or_create_classification
from data_access_logic.idea.form import IdeaCreateForm
from data_access_logic.idea.record import IdeaRecord
from db.child_lists import replaced_histories
from db.schema import Idea, IdeaHistory


class CommitIdea(CommitEntrypoint):
    """アイデアを足す。本文は作者だけが読むので、確定のあとに AI(事実確認・ミームの抜き出し)を回さない。"""

    model = Idea

    def __init__(self, idea: IdeaCreateForm):
        self.idea = idea

    def execute(self, s: Session) -> IdeaRecord:
        form = self.idea
        self.check_knowers(s, form)
        self.check_exists(s, Idea, form.parent_idea_id, "parent_idea_id")

        record = Idea()
        form.write_to(record)
        # 親を渡されていなければ、kind の分類アイデアを履歴の行の場所から探し、無ければ作って親にする。
        # ただし、いま作っているのがまさにその分類自身(name == kind)なら、自分自身の親を探しに行かない
        if form.parent_idea_id is None and form.name != form.kind:
            location_id = next((row.location_id for row in form.histories if row.location_id is not None), None)
            classification = find_or_create_classification(s, form.kind, location_id)
            if classification is not None:
                record.parent_idea_id = classification.id
        record.histories = replaced_histories([], form.histories, IdeaHistory)
        s.add(record)
        self.finalize(s, record)
        return IdeaRecord.model_validate(record)
