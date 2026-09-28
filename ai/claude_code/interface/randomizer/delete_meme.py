#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import Meme


class DeleteMeme(CommitDraft):
    model = Meme

    def __init__(self, meme_id: int):
        self.meme_id = meme_id

    def execute(self, session) -> dict:
        record = self.get_or_raise(session, int(self.meme_id), "ミーム")

        data = {"id": record.id, "category": record.category, "text": record.text}
        session.delete(record)
        return data
