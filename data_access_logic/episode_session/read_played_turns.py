#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_session.record import PlayedTurn
from data_access_logic.episode_session.turns import seen_lines, session_select
from db.schema import EpisodeCharacterSession


class ReadPlayedTurns(SessionEntrypoint):
    """人物役が、話のセッションで自分がもう動いた手番(見聞きしたこと・要求と自分の一手)を、手番の順に読む。
    手番をある行から演じ直すとき、起こし直した人物役がそれまでの場面を掴み直すために読む。ほかの人物の行は入らない。"""

    def __init__(self, episode_id: int, character_id: int):
        self.episode_id = episode_id
        self.character_id = character_id

    def execute(self, s: Session) -> list[PlayedTurn]:
        rows = s.scalars(session_select(self.episode_id).where(
            EpisodeCharacterSession.character_id == self.character_id,
            EpisodeCharacterSession.closing.is_(False),
            EpisodeCharacterSession.action.is_not(None))).all()
        return [PlayedTurn(id=row.id, seen=seen_lines(s, row), request=row.request, thought=row.thought, action=row.action,
                           speech=row.speech, aim=row.aim)
                for row in rows]
