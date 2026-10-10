#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import AppearanceSerialized, appearance_of
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query
from db.schema import Character
from db.stamp import Stamp


class ReadAppearance(SessionEntrypoint):
    """初対面の相手から見て分かること(種別・歳・性別・背丈・体格・装い・外見)を読む。名前は入れない。
    語り部が、初対面の人物の状況の差分を書くときに使う。"""

    def __init__(self, character_id: int, time: Stamp | str):
        self.character_id = character_id
        self.time = time

    def execute(self, s: Session) -> AppearanceSerialized:
        time = Stamp.parse(self.time)
        if time is None:
            raise ValueError(f"時刻が読めない: {self.time!r}")
        return appearance_of(common_query.get_row(s, Character, self.character_id), time)
