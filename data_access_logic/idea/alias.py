#!/usr/bin/env python3
"""アイデアの作中での呼び名を選ぶ。

呼び名は `idea_history` の子行(`Idea.histories`)として持ち、本質のアイデア自体は設定上の
表現のまま書く。場所・時代ごとの呼び方は `idea_history` の `location_id`・`start`・`end` で持つ。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.query import common_query, dictionary_query
from db.schema import IdeaHistory
from db.stamp import Stamp


def called(s: Session, idea_ids: list[int], location_id: int | None = None,
           time: Stamp | None = None) -> dict[int, IdeaHistory]:
    """アイデアの id ごとに、その場所・時代で使う履歴(呼び名)。当てはまる履歴が無い id は入らない。

    場所が近い履歴を先に、同じ近さなら使い始めの遅い履歴を先に選ぶ。場所・時代の列が空の履歴は最後。
    """
    ids = list(dict.fromkeys(idea_ids))
    if not ids:
        return {}
    location_ids = common_query.idea_scope_ids(s, location_id) if location_id is not None else None
    rows = s.scalars(dictionary_query.histories_select(ids, location_ids, time)).all()
    nearness = {id_: rank for rank, id_ in enumerate(location_ids or [])}
    chosen: dict[int, IdeaHistory] = {}
    for history in sorted(rows, key=lambda history: nearness.get(history.location_id, len(nearness))):
        chosen.setdefault(history.idea_id, history)
    return chosen
