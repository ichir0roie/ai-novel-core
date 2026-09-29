#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.time_keeper import generated_content
from data_access_logic.entrypoint import Entrypoint
from db.schema import get_env_session

__all__ = ["RefreshGeneratedContent"]


class RefreshGeneratedContent(Entrypoint):
    def result(self) -> generated_content.RefreshedAll:
        with get_env_session() as session:
            return generated_content.refresh_all(session, ai_client)
