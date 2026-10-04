#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows import refresh
from data_access_logic.flows.refresh import ExtractedMemes

__all__ = ["ExtractMemes"]


class ExtractMemes(Entrypoint):
    def __init__(self, fact_check: bool = True, ai: AIClient = ai_client):
        self.fact_check = fact_check
        self.ai = ai

    def result(self) -> ExtractedMemes:
        return refresh.extract_memes(self.fact_check, self.ai)
