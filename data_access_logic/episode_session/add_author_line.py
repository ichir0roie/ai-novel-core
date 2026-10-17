#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_session.record import SessionRecord
from data_access_logic.episode_session.turns import write_author_line
from db.schema import Episode


class AddAuthorLine(CommitEntrypoint):
    """作者の発言(チャットで出した場面・指示、画面の Continue)を話のセッションに入れる。作者の番ならその行に入れて番を語り部へ返し、
    語り部の番なら作者の行を新しく挟む(手番は待たせない)。"""


    def __init__(self, episode_id: int, text: str):
        self.episode_id = episode_id
        self.text = text

    def execute(self, s: Session) -> SessionRecord:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        if not self.text.strip():
            raise ValueError("text が空")
        record = write_author_line(s, self.episode_id, self.text)
        self.finalize(s, record)
        return record_of(s, SessionRecord, record)
