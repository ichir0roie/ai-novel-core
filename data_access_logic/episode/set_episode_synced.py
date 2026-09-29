#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.query import common_query
from db.schema import Episode


class SetEpisodeSynced(CommitEntrypoint):
    model = Episode

    def __init__(self, episode_id: int, synced: bool = True):
        self.episode_id = episode_id
        self.synced = synced

    def execute(self, session) -> EpisodeRecord:
        record = common_query.get_row(session, Episode, self.episode_id)
        record.synced = self.synced
        session.flush()
        return record_of(session, EpisodeRecord, record)
