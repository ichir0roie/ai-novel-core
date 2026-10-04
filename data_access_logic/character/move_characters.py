#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character import steps
from data_access_logic.character.record import CharacterMove
from data_access_logic.entrypoint import CommitEntrypoint
from db.stamp import Stamp


class MoveCharacters(CommitEntrypoint):
    """人物ごとの移動先(`CharacterMove` のリスト)で居場所を書き換える。`time` に続いている居場所の行を `time` で閉じ、
    移動先の行を `time` から足す。人物・場所が無ければ止める。書き換えた移動を返す。"""

    def __init__(self, moves: list[CharacterMove], time: Stamp | str):
        self.moves = moves
        self.time = time

    def execute(self, s: Session) -> list[CharacterMove]:
        time = Stamp.parse(self.time)
        if time is None:
            raise ValueError("time(移した時刻)が空")
        return steps.move_characters(s, steps.MovesForm(moves=self.moves, time=time))
