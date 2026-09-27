#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story._base import StoryCommit
from db.schema import Episode
from db.schema_pydantic import to_dict


class SetEpisodeSynced(StoryCommit):
    model = Episode

    def __init__(self, episode_id: int, synced: bool = True):
        self.episode_id = episode_id
        self.synced = synced

    def execute(self, session) -> dict:
        record = session.get(Episode, int(self.episode_id))
        if record is None:
            raise UnknownRecordError(f"id={self.episode_id} という話が見つからない")
        record.synced = bool(self.synced)
        return to_dict(record)
