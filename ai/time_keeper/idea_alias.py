#!/usr/bin/env python3
"""アイデアの作中での呼び名を選ぶ。

呼び名は `idea_recognition` の子行(`Idea.recognitions`)として持ち、本質のアイデア自体は設定上の
表現のまま書く。場所・時代ごとの呼び方は `idea_recognition` の `location_id`・`start`・`end` で持つ。
"""
from __future__ import annotations

from data_access_logic.query import common_query, dictionary_query
from db.schema import Idea, IdeaRecognition, Session, resolve_idea_text
from db.stamp import Stamp


def called(session: Session, idea_ids, place_id: int | None = None, time=None) -> dict[int, IdeaRecognition]:
    """アイデアの id ごとに、その場所・時代で使う認識(呼び名)。当てはまる認識が無い id は入らない。

    場所が近い認識を先に、同じ近さなら使い始めの遅い認識を先に選ぶ。場所・時代の列が空の認識は最後。
    """
    ids = list(dict.fromkeys(idea_ids))
    if not ids:
        return {}
    place_ids = common_query.idea_scope_ids(session, place_id) if place_id is not None else None
    rows = session.scalars(dictionary_query.recognitions_select(
        ids, place_ids, Stamp.parse(time))).all()
    nearness = {id_: rank for rank, id_ in enumerate(place_ids or [])}
    chosen: dict[int, IdeaRecognition] = {}
    for recognition in sorted(rows, key=lambda recognition: nearness.get(recognition.location_id, len(nearness))):
        chosen.setdefault(recognition.idea_id, recognition)
    return chosen


def name_of(idea: Idea, called: dict[int, IdeaRecognition]) -> str:
    recognition = called.get(idea.id)
    return recognition.name if recognition is not None else idea.name


def text_of(idea: Idea, called: dict[int, IdeaRecognition], time=None) -> str:
    """認識の注釈(作中での受け止め方)を前に、本質の本文を後ろに並べる。

    `time` を渡すと、その時刻に効く追記(`IdeaNote`)まで基本の本文に積み重ねた本文を使う。
    """
    recognition = called.get(idea.id)
    parts = (recognition.detail if recognition is not None and recognition.detail else "",
             resolve_idea_text(idea.text, idea.notes, time))
    return " ".join(part for part in parts if part)
