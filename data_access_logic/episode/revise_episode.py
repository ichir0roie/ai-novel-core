#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeReviseForm
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.flows import commit


class ReviseEpisode(CommitEntrypoint):
    """本文のある話の本文だけを直す(推敲)。同期フラグを保ち、登場人物の居場所・関係は本文から動かさない。"""

    def __init__(self, episode: EpisodeReviseForm):
        self.episode = episode

    def execute(self, s: Session) -> EpisodeRecord:
        return steps.revise_episode(s, self.episode)

    # 確定のあとは、ミームの抜き出しと要約だけを AI で追いかける(`flows/commit.py`)
    def result(self) -> EpisodeRecord:
        return commit.revise_episode(self.episode)
