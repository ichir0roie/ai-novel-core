#!/usr/bin/env python3
"""
    CheckFacts("oracle").show()            まだ検めていない oracle をすべて検める
    CheckFacts("meme", limit=10).show()    まだ検めていないミームを 10 件だけ検める
    CheckFacts("oracle", ids=[30]).show()  名指ししたものを検め直す

アイデアの本文は作者だけが読むので検めない。`{"checked": 検めた件数}` を返す。
"""
from __future__ import annotations

from ai.claude_code import ai_client, fact_checker
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows.fact_check import check_facts

__all__ = ["CheckFacts"]


class CheckFacts(Entrypoint):
    def __init__(self, table: str, ids: list[int] | None = None, limit: int | None = None, ai: AIClient = ai_client):
        if table not in fact_checker.MODELS:
            raise ValueError(f"table は {'/'.join(fact_checker.MODELS)} のいずれか: {table!r}")
        self.table = table
        self.ids = ids
        self.limit = limit
        self.ai = ai

    def result(self) -> fact_checker.FactChecked:
        return check_facts(self.ai, self.table, self.ids, self.limit)
