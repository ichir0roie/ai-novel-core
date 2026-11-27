#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows import episode


class SummarizedEpisodes(BaseModel):
    episodes_summarized: int


class SummarizeEpisodes(Entrypoint):
    """話の本文の要約(人物役が「居合わせた話」として読む)を、本文に揃える。`episode_id` を渡せば、その話と、その話の登場人物が
    居合わせた前の話だけ(話の人物役を起こす前に回す)。省けば、要約が無いか本文と食い違っているすべての話。作り直した件数を返す。"""

    def __init__(self, episode_id: int | None = None, ai: AIClient = ai_client):
        self.episode_id = episode_id
        self.ai = ai

    def result(self) -> SummarizedEpisodes:
        return SummarizedEpisodes(episodes_summarized=episode.summarize_episodes(self.episode_id, self.ai))
