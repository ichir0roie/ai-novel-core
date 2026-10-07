#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.meme.record import MemeRecord
from data_access_logic.query import common_query
from db.schema import Meme


class DeleteMeme(CommitEntrypoint):
    """ミームを消す。GUI の一覧で選んだものをまとめて消すので、id の配列で受ける。
    アンチミームも一緒に消す(残すと対の無いミームとして、消したミームに近いアンチミームを作り直すため)。"""


    def __init__(self, meme_ids: list[int]):
        self.meme_ids = meme_ids

    def execute(self, s: Session) -> list[MemeRecord]:
        records = [common_query.get_row(s, Meme, meme_id) for meme_id in self.meme_ids]
        ids = {record.id for record in records}
        for record in list(records):
            if record.anti_meme_id is not None and record.anti_meme_id not in ids:
                ids.add(record.anti_meme_id)
                records.append(common_query.get_row(s, Meme, record.anti_meme_id))
        deleted = [MemeRecord.model_validate(record) for record in records]
        for record in records:
            s.delete(record)
        return deleted
