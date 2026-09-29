#!/usr/bin/env python3
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import summary as episode_summary
from data_access_logic.episode.record import EpisodeSummaryRecord
from data_access_logic.query import common_query
from db.schema import Episode

logger = logging.getLogger(__name__)


class RewriteEpisodeSummary(SessionEntrypoint):
    """本文が変わっていなくても、話の概要と文体の覚え書き(`episode_summary`)を作り直す。"""

    def __init__(self, episode_ids: list[int], ai: AIClient = ai_client):
        self.episode_ids = episode_ids
        self.ai = ai

    def execute(self, s: Session) -> list[EpisodeSummaryRecord]:
        episodes = [common_query.get_row(s, Episode, episode_id) for episode_id in self.episode_ids]
        rewritten = []
        for episode in episodes:
            episode_id = episode.id
            row = episode_summary.rewrite_summary(s, self.ai, episode)
            if row is None:
                logger.warning("話 id=%s の要約を作れなかった(本文が空か、AI が答えなかった)", episode_id)
                continue
            rewritten.append(EpisodeSummaryRecord.model_validate(row))
        return rewritten
