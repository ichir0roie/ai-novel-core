#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.meme.record import MemeRecord
from data_access_logic.query import common_query
from db.schema import Meme


class DeleteMeme(CommitEntrypoint):
    """ミームを消す。GUI の一覧で選んだものをまとめて消すので、id の配列で受ける。"""

    model = Meme

    def __init__(self, meme_ids: list[int]):
        self.meme_ids = meme_ids

    def execute(self, s: Session) -> list[MemeRecord]:
        deleted = []
        for meme_id in self.meme_ids:
            record = common_query.get_row(s, Meme, meme_id)
            deleted.append(MemeRecord.model_validate(record))
            s.delete(record)
        return deleted
