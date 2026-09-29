#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client, fact_checker
from ai.claude_code.interface._base import Entrypoint
from data_access_logic.meme.extractor import refresh
from db.schema import get_env_session

__all__ = ["ExtractMemes"]


class ExtractMemes(Entrypoint):
    def __init__(self, fact_check: bool = True):
        self.fact_check = fact_check

    def run(self) -> int:
        with get_env_session() as session:
            last_id = fact_checker.last_meme_id(session)
            added = refresh(session, ai_client)
            if self.fact_check:
                fact_checker.check_new_memes(session, last_id)
            return added
