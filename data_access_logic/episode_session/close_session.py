#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_session.record import SessionRecord
from db.schema import Episode, EpisodeCharacter, EpisodeCharacterSession


class CloseSession(CommitEntrypoint):
    """話が終わったとき、セッションに出た人物と話の登場人物のすべてに終了の行を足す。人物役はそれを読んで止まる。

    人物役は登場人物ごとに起きているので、一度も番が回らなかった人物にも足さないと、その人物役が待ち続ける。
    """


    def __init__(self, episode_id: int, request: str = "話はここで終わり。止まってよい。"):
        self.episode_id = episode_id
        self.request = request

    def execute(self, s: Session) -> list[SessionRecord]:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        character_ids = s.scalars(select(EpisodeCharacterSession.character_id)
                                  .where(EpisodeCharacterSession.episode_id == self.episode_id)
                                  .order_by(EpisodeCharacterSession.id)).all()
        cast_ids = s.scalars(select(EpisodeCharacter.character_id)
                             .where(EpisodeCharacter.episode_id == self.episode_id, EpisodeCharacter.mentioned.is_(False))
                             .order_by(EpisodeCharacter.id)).all()
        records = []
        for character_id in dict.fromkeys([*character_ids, *cast_ids]):
            record = EpisodeCharacterSession(
                episode_id=self.episode_id, character_id=character_id, request=self.request, closing=True)
            s.add(record)
            self.finalize(s, record)
            records.append(record_of(s, SessionRecord, record))
        return records
