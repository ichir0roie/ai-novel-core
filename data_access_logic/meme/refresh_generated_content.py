#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows import refresh
from data_access_logic.flows.refresh import RefreshedAll

__all__ = ["RefreshGeneratedContent"]


# 数は、作り直した要約の件数
class RefreshGeneratedContent(Entrypoint):
    def __init__(self, ai: AIClient = ai_client):
        self.ai = ai

    def result(self) -> RefreshedAll:
        return refresh.refresh_generated_content(self.ai)
