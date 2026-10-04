#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode.record import EpisodeHead
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacter, EpisodeCharacterSession, EpisodeIdea


class DeleteEpisode(CommitEntrypoint):

    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> EpisodeHead:
        record = common_query.get_row(s, Episode, self.episode_id)
        deleted = EpisodeHead.model_validate(record)
        # 関連は noload なので、cascade に頼らず中間テーブルを先に消す
        for model in (EpisodeCharacter, EpisodeIdea, EpisodeCharacterSession):
            s.execute(delete(model).where(model.episode_id == record.id))
        s.delete(record)
        return deleted
