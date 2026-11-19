#!/usr/bin/env python3
"""人物・アイデア・場所を作品に置く入口。時刻はその作品の暦で数える。作品の無い行を一度に振り分けるのに使い、
置き直しは直した時刻(`updated_at`)を進めず、行の出自(AI の行か)も変えない(中身を直したことにしない。`db.writer.rewriting`)。"""
from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.record import PlacedRows
from db import writer
from db.postgres.timestamps import keep_updated_at
from db.schema import Character, Idea, Location, Story

_MODELS = {"character": Character, "idea": Idea, "location": Location}


class PlaceInStory(CommitEntrypoint):
    def __init__(self, story_id: int, table: Literal["character", "idea", "location"], ids: list[int]):
        self.story_id = story_id
        self.table = table
        self.ids = ids

    def execute(self, s: Session) -> PlacedRows:
        common_query.get_row(s, Story, self.story_id)
        model = _MODELS[self.table]
        rows = s.scalars(select(model).where(model.id.in_(self.ids))).all()
        missing = sorted(set(self.ids) - {row.id for row in rows})
        if missing:
            raise ValueError(f"{self.table} に無い id: {missing}")
        keep_updated_at(s.connection())
        with writer.rewriting():
            for row in rows:
                row.story_id = self.story_id
            s.flush()
        return PlacedRows(story_id=self.story_id, table=self.table, ids=sorted(row.id for row in rows))
