#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import ColumnElement, Select, and_, false, func, or_, select, true
from sqlalchemy.orm import aliased

from data_access_logic.query.period import alive_at, dated_alive_at
from db.schema import Idea, IdeaHistory
from db.stamp import Stamp


def _placed(row: type[IdeaHistory], location_ids: Collection[int]) -> ColumnElement[bool]:
    return or_(row.location_id.is_(None), row.location_id.in_(list(location_ids)))


def idea_in_scope(location_ids: Collection[int] | None = None, time: Stamp | None = None) -> ColumnElement[bool]:
    """`location_ids` は現在地から最上位までの場所(`common_query.idea_scope_ids`)。

    アイデアの効く場所・時期は本体に持たず、履歴の行で持つ。場所・期間の当たる行が一つでもあれば効く。
    `time` を渡したときは、始まり(`start`)の決まった行が `time` に掛かるものだけが当たる。
    その時刻にもうあるのかが分からないアイデアを渡すと、後の時代の設定が前の時代に紛れ込むので、
    始まりの空いた行しか無いアイデアと、履歴の行の無いアイデアは時期未定として外す。
    `time` を渡さなければ、履歴の行の無いアイデアはどこでも効く。
    """
    if location_ids is None and time is None:
        return true()
    # 呼び名の検索で外側の問い合わせが IdeaHistory を結合していても、それと混ざらないよう別名にする
    row = aliased(IdeaHistory)
    rows = select(row.id).where(row.idea_id == Idea.id).correlate(Idea)
    placed = []
    if location_ids is not None:
        placed.append(_placed(row, location_ids))
    if time is not None:
        placed.append(dated_alive_at(row, time))
        return rows.where(*placed).exists()
    return or_(~rows.exists(), rows.where(*placed).exists())


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
    return (select(IdeaHistory)
            .where(IdeaHistory.idea_id.in_(list(essence_ids)), history_in_scope(location_ids, time))
            .order_by(IdeaHistory.start.desc().nulls_last(), IdeaHistory.id))


def ideas_by_keywords_select(keywords: Collection[str], location_ids: Collection[int] | None = None,
                             time: Stamp | None = None) -> Select:
    """名前か本文(基本の本文、その場所・時代の作中の呼び名 `IdeaHistory`)に
    `keywords` のどれかを含むアイデア。呼び名を左外部結合するので、呼び名の無いアイデアも
    (基本の本文で当たれば)漏れない。"""
    keywords = [keyword for keyword in keywords if keyword]
    if not keywords:
        return select(Idea).where(false())
    essence_hit = or_(*(Idea.name.contains(keyword, autoescape=True) for keyword in keywords),
                      *(Idea.text.contains(keyword, autoescape=True) for keyword in keywords))
    history_hit = and_(
        or_(*(IdeaHistory.name.contains(keyword, autoescape=True) for keyword in keywords),
           *(IdeaHistory.detail.contains(keyword, autoescape=True) for keyword in keywords)),
        history_in_scope(location_ids, time))
    # 呼び名の行で当たっても、アイデアそのものが場所・時代の外なら返さない
    return (select(Idea)
            .outerjoin(IdeaHistory, IdeaHistory.idea_id == Idea.id)
            .where(or_(essence_hit, history_hit), idea_in_scope(location_ids, time))
            .distinct()
            .order_by(Idea.id))


def first_start(location_ids: Collection[int]) -> ColumnElement:
    """`location_ids` の場所で効く履歴の行のうち、一番早い始まり。始まりの空いた行は数えない。"""
    row = aliased(IdeaHistory)
    return (select(func.min(row.start))
            .where(row.idea_id == Idea.id, _placed(row, location_ids), row.start.is_not(None))
            .correlate(Idea)
            .scalar_subquery())


def later_ideas_select(location_ids: Collection[int], time: Stamp) -> Select:
    """`time` より後に始まる、`location_ids` の場所で効くアイデア。"""
    started = first_start(location_ids)
    return (select(Idea)
            .where(started > time)
            .order_by(started, Idea.id))
