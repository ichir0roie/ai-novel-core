#!/usr/bin/env python3
"""アイデア `source_id`(主に候補)を `target_id` へまとめる、claude が呼ぶ入口。

`source_id` に結んであった出来事・話・人物と、`source_id` の認識(`idea_recognition`。作中での呼び名)は
`target_id` へ付け替え、`source_id` は消す。
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.idea.links import relink
from data_access_logic.idea.record import IdeaName
from db.schema import Idea


class MergedIdea(BaseModel):
    merged: IdeaName
    into: IdeaName
    links_moved: int


class MergeIdea(CommitDraft):
    model = Idea

    def __init__(self, source_id: int, target_id: int):
        self.source_id = source_id
        self.target_id = target_id

    def execute(self, session) -> MergedIdea:
        if self.source_id == self.target_id:
            raise ValueError("source_id と target_id が同じ")
        source = self.get_or_raise(session, self.source_id, "アイデア(source_id)")
        target = self.get_or_raise(session, self.target_id, "アイデア(target_id)")
        if session.scalars(select(Idea.id).where(Idea.parent_idea_id == source.id)).first() is not None:
            raise ValueError(f"source_id={self.source_id} には下位のアイデアが残っている。先に繋ぎ直す")

        for recognition in list(source.recognitions):
            source.recognitions.remove(recognition)
            target.recognitions.append(recognition)
        merged = MergedIdea(merged=IdeaName.model_validate(source), into=IdeaName.model_validate(target),
                            links_moved=relink(session, source.id, target.id))
        session.delete(source)
        return merged
