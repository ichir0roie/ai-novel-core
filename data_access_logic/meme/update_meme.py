#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.meme.form import MemeUpdateForm
from data_access_logic.meme.record import MemeRecord
from data_access_logic.query import common_query
from db.schema import Meme


class UpdateMeme(CommitEntrypoint):
    model = Meme

    def __init__(self, meme: MemeUpdateForm):
        self.meme = meme

    def execute(self, session: Session) -> MemeRecord:
        record = common_query.get_row(session, Meme, self.meme.id)
        self.meme.write_changes_to(record)
        self.finalize(session, record)
        return MemeRecord.model_validate(record)
