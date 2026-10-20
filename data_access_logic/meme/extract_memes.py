#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows import refresh
from data_access_logic.flows.refresh import ExtractedMemes
from data_access_logic.source_text import SourceRow

__all__ = ["ExtractMemes"]


# `rows` は抜き出す元の行(`table` は oracle / event / episode)
class ExtractMemes(Entrypoint):
    def __init__(self, rows: list[SourceRow], fact_check: bool = True, ai: AIClient = ai_client):
        self.rows = rows
        self.fact_check = fact_check
        self.ai = ai

    def result(self) -> ExtractedMemes:
        return refresh.extract_memes(self.rows, self.fact_check, self.ai)
