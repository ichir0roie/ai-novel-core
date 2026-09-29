#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.story._base import StoryCommit
from data_access_logic.episode.record import EpisodeRecord
from db.schema import Episode


class SetEpisodeSynced(StoryCommit):
    model = Episode

    def __init__(self, episode_id: int, synced: bool = True):
        self.episode_id = episode_id
        self.synced = synced

    def execute(self, session) -> EpisodeRecord:
        record = self.get_or_raise(session, self.episode_id, "話")
        record.synced = self.synced
        session.flush()
        return EpisodeRecord.model_validate(reloaded(session, record, selectinload(Episode.episode_characters)))
