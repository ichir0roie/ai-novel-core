#!/usr/bin/env python3
"""ミームを手で足す入口。抜き出し(`ExtractMemes`)ではなくユーザが書いたものなので、
`confirmed` を渡さなければ 承認 で入れる。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.meme.form import MemeCreateForm
from data_access_logic.meme.record import MemeRecord
from db.schema import Meme


class CommitMeme(CommitEntrypoint):
    model = Meme

    def __init__(self, meme: MemeCreateForm):
        self.meme = meme

    def execute(self, s: Session) -> MemeRecord:
        record = Meme()
        self.meme.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return MemeRecord.model_validate(record)
