#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode.record import EpisodeRecord


# 確定のあとに AI を回さない。本文を世界に反映するのは、手番を回した話は `tool.episode_session apply`、回していない話は `ReflectEpisode`
class CommitEpisode(CommitEntrypoint):
    def __init__(self, episode: EpisodeCommitForm):
        self.episode = episode

    def execute(self, s: Session) -> EpisodeRecord:
        return steps.commit_episode(s, self.episode)
