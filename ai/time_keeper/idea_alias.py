#!/usr/bin/env python3
"""アイデアの作中での呼び名を選ぶ。

呼び名も一つのアイデアで、`alias_of_idea_id` で本質のアイデアを指す。本質のアイデアは設定上の表現のまま書き、
場所・時代ごとの呼び方は呼び名の側の `location_id`・`start`・`end` で持つ。
"""
from __future__ import annotations

from sqlalchemy import select

from data_access_logic.query import common_query, dictionary_query
from db.schema import Idea, Session
from db.stamp import Stamp


def essences(session: Session, ideas) -> list[Idea]:
    """呼び名を本質のアイデアに置き換え、重なりを除く(順は保つ)。"""
    found: dict[int, Idea] = {}
    for idea in ideas:
        essence = session.get(Idea, idea.alias_of_idea_id) if idea.alias_of_idea_id is not None else None
        essence = essence or idea
        found.setdefault(essence.id, essence)
    return list(found.values())


def called(session: Session, essence_ids, place_id: int | None = None, time=None,
          confirmed_only: bool = True) -> dict[int, Idea]:
    """本質のアイデアの id ごとに、その場所・時代で使う呼び名。当てはまる呼び名が無い id は入らない。

    場所が近い呼び名を先に、同じ近さなら使い始めの遅い呼び名を先に選ぶ。場所・時代の列が空の呼び名は最後。
    `confirmed_only` を false にすると、まだ確かめていない呼び名(`confirmed=false`)も含める。
    """
    ids = list(dict.fromkeys(essence_ids))
    if not ids:
        return {}
    place_ids = common_query.idea_scope_ids(session, place_id) if place_id is not None else None
    rows = session.scalars(dictionary_query.aliases_select(
        ids, place_ids, Stamp.parse(time), confirmed_only=confirmed_only)).all()
    nearness = {id_: rank for rank, id_ in enumerate(place_ids or [])}
    chosen: dict[int, Idea] = {}
    for alias in sorted(rows, key=lambda alias: nearness.get(alias.location_id, len(nearness))):
        chosen.setdefault(alias.alias_of_idea_id, alias)
    return chosen


def name_of(idea: Idea, aliases: dict[int, Idea]) -> str:
    alias = aliases.get(idea.id)
    return alias.name if alias is not None else idea.name


def text_of(idea: Idea, aliases: dict[int, Idea]) -> str:
    """呼び名の本文(作中での受け止め方)を前に、本質の本文を後ろに並べる。"""
    alias = aliases.get(idea.id)
    parts = ((alias.text or "").strip() if alias is not None else "", (idea.text or "").strip())
    return " ".join(part for part in parts if part)


def check(session: Session, idea_id: int | None, alias_of_idea_id: int | None) -> None:
    """`idea_id` を `alias_of_idea_id` の呼び名にしてよいか。呼び名は一段だけ(呼び名の呼び名は持たない)。"""
    if alias_of_idea_id is None:
        return
    if alias_of_idea_id == idea_id:
        raise ValueError(f"alias_of_idea_id={alias_of_idea_id} が自分自身を指している")
    essence = session.get(Idea, alias_of_idea_id)
    if essence is None:
        raise ValueError(f"alias_of_idea_id={alias_of_idea_id} というアイデアが見つからない")
    if essence.alias_of_idea_id is not None:
        raise ValueError(f"alias_of_idea_id={alias_of_idea_id} は呼び名。本質のアイデア"
                         f"(id={essence.alias_of_idea_id})を指す")
    if idea_id is not None and session.scalars(
            select(Idea.id).where(Idea.alias_of_idea_id == idea_id)).first() is not None:
        raise ValueError(f"idea_id={idea_id} には呼び名が付いているので、呼び名にはできない")
