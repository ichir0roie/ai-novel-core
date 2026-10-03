#!/usr/bin/env python3
"""アイデア `source_id`(主に候補)を `target_id` へまとめる、claude が呼ぶ入口。

`source_id` に結んであった話と、`source_id` の履歴(`idea_history`。作中での呼び名)は
`target_id` へ付け替え、`source_id` は消す。
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.links import relink
from data_access_logic.idea.record import IdeaName
from data_access_logic.query import common_query
from db.schema import Idea


class MergedIdea(BaseModel):
    merged: IdeaName
    into: IdeaName
    links_moved: int


class MergeIdea(CommitEntrypoint):
    model = Idea

    def __init__(self, source_id: int, target_id: int):
        self.source_id = source_id
        self.target_id = target_id

    def execute(self, s: Session) -> MergedIdea:
        if self.source_id == self.target_id:
            raise ValueError("source_id と target_id が同じ")
        source = common_query.get_row(s, Idea, self.source_id)
        target = common_query.get_row(s, Idea, self.target_id)
        if s.scalars(select(Idea.id).where(Idea.parent_idea_id == source.id)).first() is not None:
            raise ValueError(f"source_id={self.source_id} には下位のアイデアが残っている。先に繋ぎ直す")

        for history in list(source.histories):
            source.histories.remove(history)
            target.histories.append(history)
        merged = MergedIdea(merged=IdeaName.model_validate(source), into=IdeaName.model_validate(target),
                            links_moved=relink(s, source.id, target.id))
        s.delete(source)
        return merged
