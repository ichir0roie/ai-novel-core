#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_session.record import TurnState
from data_access_logic.episode_session.turns import turn_of


class ReadTurn(SessionEntrypoint):
    """人物役が、話のセッションでいま自分の番か(turn)、待つか(waiting)、話が終わったか(closed)を読む。"""

    def __init__(self, episode_id: int, character_id: int):
        self.episode_id = episode_id
        self.character_id = character_id

    def execute(self, s: Session) -> TurnState:
        return turn_of(s, self.episode_id, self.character_id)
