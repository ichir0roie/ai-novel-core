#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.episode.record import EpisodeSummaryRecord
from data_access_logic.flows import episode


class RewriteEpisodeSummary(Entrypoint):
    """本文が変わっていなくても、話の概要(`summary_text`)を作り直す。"""

    def __init__(self, episode_ids: list[int], ai: AIClient = ai_client):
        self.episode_ids = episode_ids
        self.ai = ai

    def result(self) -> list[EpisodeSummaryRecord]:
        return episode.rewrite_episode_summary(self.episode_ids, self.ai)
