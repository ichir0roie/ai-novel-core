#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.style_preference import extras
from data_access_logic.style_preference.record import WritingStyleRecord


class ReadWritingStyle(SessionEntrypoint):
    """このセッションの Claude がプロット・来歴・アイデア・関係など、話の本文でない文を書く前に読む書き方。

    固定の文面に、文体の好みのうち効く範囲が全体の行を足したもの。AI に書かせる文には、同じ書き方が毎回足される
    (`ai/claude_code/ai_client.generate`)。話の本文の書き方は `ReadEpisodeBrief` の「書き方」に入る。
    """

    def execute(self, s: Session) -> WritingStyleRecord:
        return WritingStyleRecord(text=extras.writing_style(s))
