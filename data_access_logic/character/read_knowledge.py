#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import KnowledgeSerialized, knowledge_of
from data_access_logic.entrypoint import SessionEntrypoint
from db.stamp import Stamp


class ReadKnowledge(SessionEntrypoint):
    """人物がその時刻に知ることのできるデータを読む。本文・来歴は、公開のものと、その人物が知る人に入ったものだけ。"""

    def __init__(self, character_id: int, time: Stamp | str):
        self.character_id = character_id
        self.time = time

    def execute(self, s: Session) -> KnowledgeSerialized:
        time = Stamp.parse(self.time)
        if time is None:
            raise ValueError(f"時刻が読めない: {self.time!r}")
        return knowledge_of(s, self.character_id, time)
