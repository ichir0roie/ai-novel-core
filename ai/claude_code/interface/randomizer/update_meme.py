#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.meme.form import MemeUpdateForm
from data_access_logic.meme.record import MemeRecord
from db.schema import Meme


class UpdateMeme(CommitDraft):
    model = Meme

    def __init__(self, meme: MemeUpdateForm):
        self.meme = meme

    def execute(self, session) -> MemeRecord:
        record = self.get_or_raise(session, self.meme.id, "ミーム")
        self.meme.write_changes_to(record)
        self.finalize(session, record)
        return MemeRecord.model_validate(record)
