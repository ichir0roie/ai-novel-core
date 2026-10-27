#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeReviseForm
from data_access_logic.episode.record import EpisodeRecord


class ReviseEpisode(CommitEntrypoint):
    """本文のある話の本文だけを直す(推敲)。確定のあとに AI を回さない。`CommitEpisode` と違い、登場人物の居場所・関係を
    本文から動かさない(昔の話を推敲すると、今の居場所がその話の頃の場所へ戻り、とうに知り合った二人に関係が重なるので)。
    推敲は筋を変えないので、ミームも出来事の種も抜き出し直さない。"""

    def __init__(self, episode: EpisodeReviseForm):
        self.episode = episode

    def execute(self, s: Session) -> EpisodeRecord:
        return steps.revise_episode(s, self.episode)
