#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.style_preference import extras
from data_access_logic.style_preference.form import WritingStyleForm
from data_access_logic.style_preference.record import WritingStyleRecord


class ReadWritingStyle(SessionEntrypoint):
    """このセッションの Claude がプロット・来歴・アイデア・関係など、話の本文でない文を書く前に読む書き方。

    書く文に合う範囲(プロット・人物・来歴・出来事・アイデア・関係など)を渡す。全体の行 → その範囲の行 の順に、db から読んで足したもの
    (作品・話の指示は本文だけに足すので、本文でない文には入らない)。AI に書かせる文には、同じ書き方が毎回足される(`ai/claude_code/ai_client.generate`)。
    話の本文の書き方は `ReadEpisodeBrief` の「書き方」に入る。
    """

    def __init__(self, writing_style: WritingStyleForm | None = None):
        self.writing_style = writing_style or WritingStyleForm()

    def execute(self, s: Session) -> WritingStyleRecord:
        return WritingStyleRecord(text=extras.writing_style(
            s, self.writing_style.scope, self.writing_style.story_id, self.writing_style.episode_id))
