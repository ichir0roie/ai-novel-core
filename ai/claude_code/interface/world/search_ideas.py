#!/usr/bin/env python3
"""アイデアをあいまい検索する、claude が呼ぶ入口。まだ確かめていない候補(`confirmed=未確認`・非承認)も返す。

    SearchIdeas("霊纏").run()
    SearchIdeas([{"keyword": "遺伝子異常", "variants": ["遺伝病", "血の病", "遺伝"]}], place_id=58, time="1200").run()

名前か本文に、キーワードか言い換えのどれかを含むアイデアを、当たり方の強い順に返す。
`place_id` を渡すとそこから最上位までの場所に置いたアイデアに、`time` を渡すとその時刻に効くアイデアに絞る。
`called` は、その場所・時刻での作中の呼び名(呼び名に当たったときは、その本質のアイデアの呼び名)。
"""
from __future__ import annotations

from ai.claude_code.interface._base import SessionEntrypoint
from ai.time_keeper import idea_alias, idea_search
from db.schema import resolve_idea_text


class SearchIdeas(SessionEntrypoint):
    def __init__(self, keywords, place_id: int | None = None, limit: int | None = None, time=None):
        self.keywords = keywords
        self.place_id = None if place_id is None else int(place_id)
        self.limit = limit
        self.time = time

    def execute(self, session) -> list[dict]:
        hits = idea_search.search(session, self.keywords, self.place_id, self.time, limit=self.limit,
                                  confirmed_only=False)
        essences = {hit.idea.id: idea_alias.essences(session, [hit.idea])[0] for hit in hits}
        called = idea_alias.called(session, [essence.id for essence in essences.values()], self.place_id, self.time,
                                   confirmed_only=False)
        return [
            {"id": hit.idea.id, "name": hit.idea.name, "kind": hit.idea.kind,
             "confirmed": hit.idea.confirmed,
             "parent_idea_id": hit.idea.parent_idea_id, "alias_of_idea_id": hit.idea.alias_of_idea_id,
             "called": idea_alias.name_of(essences[hit.idea.id], called),
             "text": resolve_idea_text(hit.idea.text, hit.idea.notes, self.time),
             "score": hit.score, "keywords": hit.keywords}
            for hit in hits]
