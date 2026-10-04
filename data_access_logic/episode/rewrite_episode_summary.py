#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode.record import EpisodeSummaryRecord
from data_access_logic.query import common_query
from data_access_logic.summary_targets import rewrite_episode_summaries
from db.schema import Episode


class RewriteEpisodeSummary(SessionEntrypoint):
    """本文が変わっていなくても、話の概要(`summary_text`)を作り直す。"""

    def __init__(self, episode_ids: list[int], ai: AIClient = ai_client):
        self.episode_ids = episode_ids
        self.ai = ai

    def execute(self, s: Session) -> list[EpisodeSummaryRecord]:
        for episode_id in self.episode_ids:
            common_query.get_row(s, Episode, episode_id)
        rewritten = rewrite_episode_summaries(s, self.ai, self.episode_ids, stale_only=False)
        return [EpisodeSummaryRecord.model_validate(episode) for episode in rewritten]
