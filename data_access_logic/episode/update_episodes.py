#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeUpdateForm
from data_access_logic.episode.record import EpisodeRecord


class UpdateEpisodes(CommitEntrypoint):
    """話をまとめて直す。GUI のタイムラインの変更モードで溜めた時刻・作品の移しを、一つのトランザクションで書く。
    一件ずつは GUI の修正(`CommitEpisode` の `execute`)と同じに書くので、同期フラグも同じく外れる。"""

    def __init__(self, episodes: list[EpisodeUpdateForm]):
        self.episodes = episodes

    def execute(self, s: Session) -> list[EpisodeRecord]:
        return [steps.commit_episode(s, episode) for episode in self.episodes]
