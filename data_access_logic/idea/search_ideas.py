#!/usr/bin/env python3
"""アイデアをあいまい検索する、claude が呼ぶ入口。まだ確かめていない候補(`confirmed=未確認`・非承認)も返す。

    SearchIdeas([IdeaTerm(keyword="霊纏")]).show()
    SearchIdeas([IdeaTerm(keyword="遺伝子異常", variants=["遺伝病", "血の病", "遺伝"])], place_id=58, time="1200").show()

名前か本文に、キーワードか言い換えのどれかを含むアイデアを、当たり方の強い順に返す。
`place_id` を渡すとそこから最上位までの場所に置いたアイデアに、`time` を渡すとその時刻に効くアイデアに絞る。
`called` は、その場所・時刻での作中の呼び名(`idea_recognition` に当たるものがあれば、その名前)。
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.idea.alias import called
from data_access_logic.idea.models import IdeaTerm
from data_access_logic.idea.search import search
from db.schema import ConfirmStatus
from db.stamp import Stamp


class FoundIdea(BaseModel):
    id: int
    name: str
    kind: str
    confirmed: ConfirmStatus
    parent_idea_id: int | None = None
    called: str
    text: str | None = None
    score: int
    keywords: list[str]


class SearchIdeas(SessionEntrypoint):
    def __init__(self, keywords: list[IdeaTerm], place_id: int | None = None, limit: int | None = None, time: Stamp | str | None = None):
        self.keywords = keywords
        self.place_id = place_id
        self.limit = limit
        self.time = Stamp.parse(time)

    def execute(self, s: Session) -> list[FoundIdea]:
        hits = search(s, self.keywords, self.place_id, self.time, limit=self.limit, confirmed_only=False)
        recognitions = called(s, [hit.idea.id for hit in hits], self.place_id, self.time)
        return [
            FoundIdea(id=hit.idea.id, name=hit.idea.name, kind=hit.idea.kind, confirmed=hit.idea.confirmed,
                      parent_idea_id=hit.idea.parent_idea_id,
                      called=recognitions[hit.idea.id].name if hit.idea.id in recognitions else hit.idea.name,
                      text=hit.idea.text, score=hit.score, keywords=hit.keywords)
            for hit in hits]
