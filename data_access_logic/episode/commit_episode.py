#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode.record import CommittedEpisode, EpisodeRecord
from data_access_logic.flows import commit


# 確定のあと(`run()` / `show()`)は、ミームの抜き出しと要約を AI で追いかけ、本文を渡したときは登場人物の居場所も移す(`flows/commit.py`)
class CommitEpisode(CommitEntrypoint):
    def __init__(self, episode: EpisodeCommitForm):
        self.episode = episode

    def execute(self, s: Session) -> EpisodeRecord:
        return steps.commit_episode(s, self.episode)

    def result(self) -> CommittedEpisode:
        return commit.commit_episode(self.episode)
