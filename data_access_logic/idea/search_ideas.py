#!/usr/bin/env python3
"""アイデアをあいまい検索する、claude が呼ぶ入口。

    SearchIdeas([IdeaDraft(keyword="霊纏")]).show()
    SearchIdeas([IdeaDraft(keyword="遺伝子異常", variants=["遺伝病", "血の病", "遺伝"])], location_id=58, time="1200").show()

名前か本文に、キーワードか言い換えのどれかを含むアイデアを、当たり方の強い順に返す。
`location_id` を渡すとそこから最上位までの場所に置いたアイデアに、`time` を渡すとその時刻に効くアイデアに絞る。
`called` は、その場所・時刻での作中の呼び名(`idea_history` に当たるものがあれば、その名前)。
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.idea.alias import called
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.idea.search import search
from db.stamp import Stamp


class FoundIdea(BaseModel):
    id: int
    name: str
    kind: str
    parent_idea_id: int | None = None
    called: str
    text: str | None = None
    score: int
    keywords: list[str]


class SearchIdeas(SessionEntrypoint):
    def __init__(self, keywords: list[IdeaDraft], location_id: int | None = None, limit: int | None = None, time: Stamp | str | None = None):
        self.keywords = keywords
        self.location_id = location_id
        self.limit = limit
        self.time = Stamp.parse(time)

    def execute(self, s: Session) -> list[FoundIdea]:
        hits = search(s, self.keywords, self.location_id, self.time, limit=self.limit)
        histories = called(s, [hit.idea.id for hit in hits], self.location_id, self.time)
        return [
            FoundIdea(id=hit.idea.id, name=hit.idea.name, kind=hit.idea.kind,
                      parent_idea_id=hit.idea.parent_idea_id,
                      called=histories[hit.idea.id].name if hit.idea.id in histories else hit.idea.name,
                      text=hit.idea.text, score=hit.score, keywords=hit.keywords)
            for hit in hits]
