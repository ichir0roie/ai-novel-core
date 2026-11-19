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
    装いは物ごとに、物の名前・今の姿・いつから身に着けているか(今からの隔たり。`character/time_sense.py`)。
    語り部が、初対面の人物の状況の差分を書くときに使う。"""

    def __init__(self, character_id: int, time: Stamp | str, episode_id: int | None = None):
        self.character_id = character_id
        self.time = time
        # 時刻を読む暦の作品を決めるだけ(`gui/api/interface.call` が引数から作品を立てる。話の作品が相手の作品より先に効く)
        self.episode_id = episode_id

    def execute(self, s: Session) -> AppearanceSerialized:
        time = Stamp.parse(self.time)
        if time is None:
            raise ValueError(f"時刻が読めない: {self.time!r}")
        return appearance_of(s, common_query.get_row(s, Character, self.character_id), time)
