#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.meme.record import MemeRecord
from data_access_logic.query import common_query
from db.schema import Meme


class DeleteMeme(CommitEntrypoint):
    model = Meme

    def __init__(self, meme_id: int):
        self.meme_id = meme_id

    def execute(self, session: Session) -> MemeRecord:
        record = common_query.get_row(session, Meme, self.meme_id)
        deleted = MemeRecord.model_validate(record)
        session.delete(record)
        return deleted
