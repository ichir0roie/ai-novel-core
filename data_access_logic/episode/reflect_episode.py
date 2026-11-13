#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.episode.outcomes import AppliedOutcomes
from data_access_logic.flows import episode


class ReflectEpisode(Entrypoint):
    """本文を確定した話(手番を回さずに書いた話)を世界に反映する。登場人物ごとの差分(この話で起きたこと・知ったことの来歴、
    知り合った相手との関係、身に着けた・外した装い、移った住まい)を AI が本文から一度に書いて入れ、セリフを拾い直す。
    手番を回した話は、人物役の差分を `tool.episode_session apply` で入れる。"""

    def __init__(self, episode_id: int, ai: AIClient = ai_client):
        self.episode_id = episode_id
        self.ai = ai

    def result(self) -> AppliedOutcomes:
        return episode.reflect_episode(self.episode_id, self.ai)
