#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import KnowledgeSerialized, knowledge_of
from data_access_logic.entrypoint import SessionEntrypoint
from db.stamp import Stamp


class ReadKnowledge(SessionEntrypoint):
    """人物がその時刻に知ることのできるデータを読む。来歴は公開の行と、その人物が知る人に入った行だけ。
    `episode_id` を渡すと、その話の登場人物の来歴も入る。"""

    def __init__(self, character_id: int, time: Stamp | str, episode_id: int | None = None):
        self.character_id = character_id
        self.time = time
        self.episode_id = episode_id

    def execute(self, s: Session) -> KnowledgeSerialized:
        time = Stamp.parse(self.time)
        if time is None:
            raise ValueError(f"時刻が読めない: {self.time!r}")
        return knowledge_of(s, self.character_id, time, self.episode_id)
