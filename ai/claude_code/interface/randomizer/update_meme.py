#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import MEME_CATEGORIES, Meme


class UpdateMeme(CommitDraft):
    model = Meme

    def __init__(self, meme: str | dict):
        self.meme = meme

    def execute(self, session) -> dict:
        data = self.parse(self.meme)
        meme_id = self.require_id(data, "直す対象のミーム")
        self.check_columns(data)
        if data.get("category") not in (None, *MEME_CATEGORIES):
            raise ValueError(f"category は {'/'.join(MEME_CATEGORIES)} のいずれか: {data['category']}")

        record = self.get_or_raise(session, meme_id, "ミーム")

        return self.apply(session, record, data)
