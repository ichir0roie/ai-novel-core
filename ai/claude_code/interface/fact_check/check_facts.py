#!/usr/bin/env python3
"""
    CheckFacts("idea").run()              まだ検めていないアイデアをすべて検める
    CheckFacts("oracle").run()            まだ検めていない oracle をすべて検める
    CheckFacts("meme", limit=10).run()    まだ検めていないミームを 10 件だけ検める
    CheckFacts("idea", ids=[30]).run()    名指ししたものを検め直す

アイデア・oracle は、検めたあと本文(検証結果の節を含む)からミームを抜き出し、足したミームも検める。
`{"checked": 検めた件数, "memes_added": 足したミームの件数}` を返す。
"""
from __future__ import annotations

from ai.claude_code import fact_checker
from ai.claude_code.interface._base import Entrypoint
from db.schema import get_env_session

__all__ = ["CheckFacts"]


class CheckFacts(Entrypoint):
    def __init__(self, table: str, ids: list[int] | None = None, limit: int | None = None):
        if table not in fact_checker.MODELS:
            raise ValueError(f"table は {'/'.join(fact_checker.MODELS)} のいずれか: {table!r}")
        self.table = table
        self.ids = ids
        self.limit = limit

    def run(self) -> dict:
        with get_env_session() as session:
            return fact_checker.check_and_extract(session, self.table, self.ids, self.limit)
