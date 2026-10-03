#!/usr/bin/env python3
"""アイデア `source_id`(主に候補)を `target_id` へまとめる、claude が呼ぶ入口。

`source_id` に結んであった出来事・話・人物と、`source_id` の認識(`idea_recognition`。作中での呼び名)は
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

        for recognition in list(source.recognitions):
            source.recognitions.remove(recognition)
            target.recognitions.append(recognition)
        for history in list(source.histories):
            source.histories.remove(history)
            target.histories.append(history)
        # 本文を知る相手は、統合先にまだいない相手だけ移す(同じ相手の行が重なると一意制約に当たる)
        known = {(knower.knower_id, knower.location_id) for knower in target.knowers}
        for knower in list(source.knowers):
            source.knowers.remove(knower)
            if (knower.knower_id, knower.location_id) not in known:
                target.knowers.append(knower)
        merged = MergedIdea(merged=IdeaName.model_validate(source), into=IdeaName.model_validate(target),
                            links_moved=relink(s, source.id, target.id))
        s.delete(source)
        return merged
