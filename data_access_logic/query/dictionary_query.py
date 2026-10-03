#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import ColumnElement, Select, and_, false, or_, select, true

from data_access_logic.query.period import alive_at
from db.schema import Idea, IdeaHistory
from db.stamp import Stamp


def idea_in_scope(location_ids: Collection[int] | None = None, time: Stamp | None = None) -> ColumnElement[bool]:
    """`location_ids` は現在地から最上位までの場所(`common_query.idea_scope_ids`)。"""
    conditions = []
    if location_ids is not None:
        conditions.append(Idea.location_id.in_(list(location_ids)))
    if time is not None:
        conditions.append(alive_at(Idea, time))
    return and_(true(), *conditions)


def history_in_scope(location_ids: Collection[int] | None = None, time: Stamp | None = None) -> ColumnElement[bool]:
    """履歴(呼び名)は、場所・時代の列が空ならどこでも・いつでも使う。
    `location_ids` / `time` を渡さなければ、その列が空の履歴だけに当たる。
    """
    location = IdeaHistory.location_id.is_(None)
    if location_ids is not None:
        location = or_(location, IdeaHistory.location_id.in_(list(location_ids)))
    if time is None:
        period = and_(IdeaHistory.start.is_(None), IdeaHistory.end.is_(None))
    else:
        period = alive_at(IdeaHistory, time)
    return and_(location, period)


def histories_select(essence_ids: Collection[int], location_ids: Collection[int] | None = None,
                        time: Stamp | None = None) -> Select:
    # 非公開の行は知る相手だけの秘密で、その場所・時代の呼び名ではない
    conditions = [IdeaHistory.idea_id.in_(list(essence_ids)), history_in_scope(location_ids, time),
                  IdeaHistory.private.is_(False)]
    return (select(IdeaHistory)
            .where(*conditions)
            .order_by(IdeaHistory.start.desc().nulls_last(), IdeaHistory.id))


def ideas_by_keywords_select(keywords: Collection[str], location_ids: Collection[int] | None = None,
                             time: Stamp | None = None) -> Select:
    """名前か本文(基本の本文、その場所・時代の作中の呼び名 `IdeaHistory`)に
    `keywords` のどれかを含むアイデア。呼び名を左外部結合するので、呼び名の無いアイデアも
    (基本の本文で当たれば)漏れない。"""
    keywords = [keyword for keyword in keywords if keyword]
    if not keywords:
        return select(Idea).where(false())
    essence_hit = and_(
        or_(*(Idea.name.contains(keyword, autoescape=True) for keyword in keywords),
           *(Idea.text.contains(keyword, autoescape=True) for keyword in keywords)),
        idea_in_scope(location_ids, time))
    history_hit = and_(
        or_(*(IdeaHistory.name.contains(keyword, autoescape=True) for keyword in keywords),
           *(IdeaHistory.detail.contains(keyword, autoescape=True) for keyword in keywords)),
        history_in_scope(location_ids, time))
    return (select(Idea)
            .outerjoin(IdeaHistory, IdeaHistory.idea_id == Idea.id)
            .where(or_(essence_hit, history_hit))
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
