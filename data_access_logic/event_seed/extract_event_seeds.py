#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows import refresh
from data_access_logic.flows.refresh import ExtractedEventSeeds
from data_access_logic.source_text import SourceRow

__all__ = ["ExtractEventSeeds"]


# `rows` は抜き出す元の行(`table` は episode / character / event)
class ExtractEventSeeds(Entrypoint):
    def __init__(self, rows: list[SourceRow], ai: AIClient = ai_client):
        self.rows = rows
        self.ai = ai

    def result(self) -> ExtractedEventSeeds:
        return refresh.extract_event_seeds(self.rows, self.ai)
