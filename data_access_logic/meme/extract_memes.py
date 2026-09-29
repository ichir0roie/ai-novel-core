#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code import ai_client, fact_checker
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.meme.extractor import refresh
from db.schema import get_env_session

__all__ = ["ExtractMemes"]


class ExtractedMemes(BaseModel):
    memes_added: int


class ExtractMemes(Entrypoint):
    def __init__(self, fact_check: bool = True):
        self.fact_check = fact_check

    def result(self) -> ExtractedMemes:
        with get_env_session() as session:
            last_id = fact_checker.last_meme_id(session)
            added = refresh(session, ai_client)
            if self.fact_check:
                fact_checker.check_new_memes(session, last_id)
            return ExtractedMemes(memes_added=added)
