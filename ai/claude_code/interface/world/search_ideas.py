#!/usr/bin/env python3
"""アイデアをあいまい検索する、claude が呼ぶ入口。まだ確かめていない候補(`confirmed=未確認`・非承認)も返す。

    SearchIdeas("霊纏").run()
    SearchIdeas([{"keyword": "遺伝子異常", "variants": ["遺伝病", "血の病", "遺伝"]}], place_id=58, time="1200").run()

名前か本文に、キーワードか言い換えのどれかを含むアイデアを、当たり方の強い順に返す。
`place_id` を渡すとそこから最上位までの場所に置いたアイデアに、`time` を渡すとその時刻に効くアイデアに絞る。
`called` は、その場所・時刻での作中の呼び名(`idea_recognition` に当たるものがあれば、その名前)。
"""
from __future__ import annotations

from ai.claude_code.interface._base import SessionEntrypoint
from ai.time_keeper import idea_alias, idea_search


class SearchIdeas(SessionEntrypoint):
    def __init__(self, keywords, place_id: int | None = None, limit: int | None = None, time=None):
        self.keywords = keywords
        self.place_id = None if place_id is None else int(place_id)
        self.limit = limit
        self.time = time

    def execute(self, session) -> list[dict]:
        hits = idea_search.search(session, self.keywords, self.place_id, self.time, limit=self.limit,
                                  confirmed_only=False)
        called = idea_alias.called(session, [hit.idea.id for hit in hits], self.place_id, self.time)
        return [
            {"id": hit.idea.id, "name": hit.idea.name, "kind": hit.idea.kind,
             "confirmed": hit.idea.confirmed,
             "parent_idea_id": hit.idea.parent_idea_id,
             "called": idea_alias.name_of(hit.idea, called),
             "text": hit.idea.text,
             "score": hit.score, "keywords": hit.keywords}
            for hit in hits]
