#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import KnownIdeasSerialized, knowing_time, known_ideas_by_words
from data_access_logic.entrypoint import SessionEntrypoint
from db.stamp import Stamp


class ReadKnownIdeas(SessionEntrypoint):
    """人物役が、手番の要求に出た語を、自分の知っているアイデアから引く。語ごとに、本質の名前か知っている呼び名の当たる
    アイデアの呼び名と受け止め方を返し、知らなければ空。時刻は `ReadKnowledge` と同じく `time`、渡さなければ話の時刻。"""

    def __init__(self, character_id: int, words: list[str], episode_id: int | None = None, time: Stamp | str | None = None):
        self.character_id = character_id
        self.words = words
        self.episode_id = episode_id
        self.time = time

    def execute(self, s: Session) -> KnownIdeasSerialized:
        return known_ideas_by_words(s, self.character_id, knowing_time(s, self.episode_id, self.time), self.words)
