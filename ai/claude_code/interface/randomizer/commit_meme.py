#!/usr/bin/env python3
"""ミームを手で足す入口。抜き出し(`ExtractMemes`)ではなくユーザが書いたものなので、
`confirmed` を渡さなければ 承認 で入れる。"""
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import MEME_CATEGORIES, ConfirmStatus, Meme
from db.schema_pydantic import to_dict


class CommitMeme(CommitDraft):
    model = Meme

    def __init__(self, meme: str | dict):
        self.meme = meme

    def execute(self, session) -> dict:
        data = self.parse(self.meme)
        data.pop("id", None)
        self.check_columns(data)
        if not (data.get("text") or "").strip():
            raise ValueError("text は必須")
        if data.get("category") not in (None, *MEME_CATEGORIES):
            raise ValueError(f"category は {'/'.join(MEME_CATEGORIES)} のいずれか: {data['category']}")
        data.setdefault("confirmed", ConfirmStatus.APPROVED)
        record = Meme(**data)
        session.add(record)
        self.finalize(session, record)
        return to_dict(record)
