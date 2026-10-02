#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import ColumnElement, Select, and_, false, or_, select, true

from data_access_logic.query.period import alive_at
from db.schema import Idea, IdeaRecognition
from db.stamp import Stamp


def idea_in_scope(location_ids: Collection[int] | None = None, time: Stamp | None = None) -> ColumnElement[bool]:
    """`location_ids` は現在地から最上位までの場所(`common_query.idea_scope_ids`)。"""
    conditions = []
    if location_ids is not None:
        conditions.append(Idea.location_id.in_(list(location_ids)))
    if time is not None:
        conditions.append(alive_at(Idea, time))
    return and_(true(), *conditions)


def recognition_in_scope(location_ids: Collection[int] | None = None, time: Stamp | None = None) -> ColumnElement[bool]:
    """認識(呼び名)は、場所・時代の列が空ならどこでも・いつでも使う。
    `location_ids` / `time` を渡さなければ、その列が空の認識だけに当たる。
    """
    location = IdeaRecognition.location_id.is_(None)
    if location_ids is not None:
        location = or_(location, IdeaRecognition.location_id.in_(list(location_ids)))
    if time is None:
        period = and_(IdeaRecognition.start.is_(None), IdeaRecognition.end.is_(None))
    else:
        period = alive_at(IdeaRecognition, time)
    return and_(location, period)


def recognitions_select(essence_ids: Collection[int], location_ids: Collection[int] | None = None,
                        time: Stamp | None = None) -> Select:
    conditions = [IdeaRecognition.idea_id.in_(list(essence_ids)), recognition_in_scope(location_ids, time)]
    return (select(IdeaRecognition)
            .where(*conditions)
            .order_by(IdeaRecognition.start.desc().nulls_last(), IdeaRecognition.id))


def ideas_by_terms_select(terms: Collection[str], location_ids: Collection[int] | None = None,
                          time: Stamp | None = None) -> Select:
    """名前か本文(基本の本文、その場所・時代の作中の呼び名 `IdeaRecognition`)に
    `terms` のどれかを含むアイデア。呼び名を左外部結合するので、呼び名の無いアイデアも
    (基本の本文で当たれば)漏れない。"""
    terms = [term for term in terms if term]
    if not terms:
        return select(Idea).where(false())
    essence_hit = and_(
        or_(*(Idea.name.contains(term, autoescape=True) for term in terms),
           *(Idea.text.contains(term, autoescape=True) for term in terms)),
        idea_in_scope(location_ids, time))
    recognition_hit = and_(
        or_(*(IdeaRecognition.name.contains(term, autoescape=True) for term in terms),
           *(IdeaRecognition.detail.contains(term, autoescape=True) for term in terms)),
        recognition_in_scope(location_ids, time))
    return (select(Idea)
            .outerjoin(IdeaRecognition, IdeaRecognition.idea_id == Idea.id)
            .where(or_(essence_hit, recognition_hit))
            .distinct()
            .order_by(Idea.id))


def ideas_by_parent_select(parent_ids: Collection[int], location_ids: Collection[int] | None = None,
                           time: Stamp | None = None) -> Select:
    return (select(Idea).where(Idea.parent_idea_id.in_(list(parent_ids)), idea_in_scope(location_ids, time))
            .order_by(Idea.id))


def later_ideas_select(location_ids: Collection[int], time: Stamp) -> Select:
    """`time` より後に始まる、`location_ids` の場所で効くアイデア。"""
    return (select(Idea)
            .where(Idea.location_id.in_(list(location_ids)), Idea.start > time)
            .order_by(Idea.start, Idea.id))
