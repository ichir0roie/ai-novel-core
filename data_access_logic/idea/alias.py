#!/usr/bin/env python3
"""アイデアの作中での呼び名を選ぶ。

呼び名は `idea_recognition` の子行(`Idea.recognitions`)として持ち、本質のアイデア自体は設定上の
表現のまま書く。場所・時代ごとの呼び方は `idea_recognition` の `location_id`・`start`・`end` で持つ。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.query import common_query, dictionary_query
from db.schema import IdeaRecognition
from db.stamp import Stamp


def called(s: Session, idea_ids: list[int], place_id: int | None = None,
           time: Stamp | None = None) -> dict[int, IdeaRecognition]:
    """アイデアの id ごとに、その場所・時代で使う認識(呼び名)。当てはまる認識が無い id は入らない。

    場所が近い認識を先に、同じ近さなら使い始めの遅い認識を先に選ぶ。場所・時代の列が空の認識は最後。
    """
    ids = list(dict.fromkeys(idea_ids))
    if not ids:
        return {}
    place_ids = common_query.idea_scope_ids(s, place_id) if place_id is not None else None
    rows = s.scalars(dictionary_query.recognitions_select(ids, place_ids, time)).all()
    nearness = {id_: rank for rank, id_ in enumerate(place_ids or [])}
    chosen: dict[int, IdeaRecognition] = {}
    for recognition in sorted(rows, key=lambda recognition: nearness.get(recognition.location_id, len(nearness))):
        chosen.setdefault(recognition.idea_id, recognition)
    return chosen
