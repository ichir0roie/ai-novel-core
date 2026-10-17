#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.episode.voices import VoiceDraft
from data_access_logic.flows import episode


class RefreshVoices(Entrypoint):
    """同じ作品の直前の五話のセリフから、話の登場人物の話し方(一人称・二人称・三人称・口調・方言)を AI に調整させ、
    話の時刻から効く行として書き戻す。書いた人物の調整案を返す。"""

    def __init__(self, episode_id: int, ai: AIClient = ai_client):
        self.episode_id = episode_id
        self.ai = ai

    def result(self) -> list[VoiceDraft]:
        return episode.refresh_voices(self.episode_id, self.ai)
