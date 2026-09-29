#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.meme.record import MemeRecord
from db.schema import Meme


class DeleteMeme(CommitDraft):
    model = Meme

    def __init__(self, meme_id: int):
        self.meme_id = meme_id

    def execute(self, session) -> MemeRecord:
        record = self.get_or_raise(session, self.meme_id, "ミーム")
        deleted = MemeRecord.model_validate(record)
        session.delete(record)
        return deleted
