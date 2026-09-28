#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import ColumnElement, Select, and_, false, or_, select, true

from db.schema import ConfirmStatus, Idea, IdeaNote, IdeaRecognition
from db.stamp import Stamp


def idea_note_in_scope(time: Stamp | None = None) -> ColumnElement[bool]:
    """`time` を渡さなければ絞らない(`idea_in_scope` と同じ)。"""
    if time is None:
        return true()
    return and_(or_(IdeaNote.start.is_(None), IdeaNote.start <= time),
                or_(IdeaNote.end.is_(None), time < IdeaNote.end))


def idea_notes_join(time: Stamp | None = None) -> ColumnElement[bool]:
    """`Idea` に `IdeaNote` を左外部結合するときの ON 条件。その時刻に効く追記だけを繋ぐ。"""
    return and_(IdeaNote.idea_id == Idea.id, idea_note_in_scope(time))


def idea_in_scope(place_ids=None, time: Stamp | None = None) -> ColumnElement[bool]:
    """`place_ids` は現在地から最上位までの場所(`common_query.idea_scope_ids`)。"""
    conditions = []
    if place_ids is not None:
        conditions.append(Idea.location_id.in_(list(place_ids)))
    if time is not None:
        conditions += [or_(Idea.start.is_(None), Idea.start <= time),
                       or_(Idea.end.is_(None), Idea.end > time)]
    return and_(true(), *conditions)


def recognition_in_scope(place_ids=None, time: Stamp | None = None) -> ColumnElement[bool]:
    """認識(呼び名)は、場所・時代の列が空ならどこでも・いつでも使う。
    `place_ids` / `time` を渡さなければ、その列が空の認識だけに当たる。
    """
    location = IdeaRecognition.location_id.is_(None)
    if place_ids is not None:
        location = or_(location, IdeaRecognition.location_id.in_(list(place_ids)))
    if time is None:
        period = and_(IdeaRecognition.start.is_(None), IdeaRecognition.end.is_(None))
    else:
        period = and_(or_(IdeaRecognition.start.is_(None), IdeaRecognition.start <= time),
                      or_(IdeaRecognition.end.is_(None), IdeaRecognition.end > time))
    return and_(location, period)


def recognitions_select(essence_ids, place_ids=None, time: Stamp | None = None) -> Select:
    conditions = [IdeaRecognition.idea_id.in_(list(essence_ids)), recognition_in_scope(place_ids, time)]
    return (select(IdeaRecognition)
            .where(*conditions)
            .order_by(IdeaRecognition.start.desc().nulls_last(), IdeaRecognition.id))


def ideas_by_keyword_select(keyword: str, confirmed_only: bool = True) -> Select:
    return ideas_by_terms_select([keyword], confirmed_only=confirmed_only)


def ideas_by_terms_select(terms, place_ids=None, time: Stamp | None = None,
                          confirmed_only: bool = True) -> Select:
    """名前か本文(基本の本文、その時代に効く追記 `IdeaNote`、その場所・時代の作中の呼び名 `IdeaRecognition`)に
    `terms` のどれかを含むアイデア。呼び名・追記を左外部結合するので、それらの無いアイデアも
    (基本の本文で当たれば)漏れない。`confirmed_only` を false にすると、
    まだ確かめていない候補(`confirmed=未確認`)も含める。"""
    terms = [term for term in terms if term]
    if not terms:
        return select(Idea).where(false())
    essence_hit = and_(
        or_(*(Idea.name.contains(term, autoescape=True) for term in terms),
           *(Idea.text.contains(term, autoescape=True) for term in terms),
           *(IdeaNote.text.contains(term, autoescape=True) for term in terms)),
        idea_in_scope(place_ids, time))
    recognition_hit = and_(
        or_(*(IdeaRecognition.name.contains(term, autoescape=True) for term in terms),
           *(IdeaRecognition.detail.contains(term, autoescape=True) for term in terms)),
        recognition_in_scope(place_ids, time))
    conditions = [or_(essence_hit, recognition_hit)]
    if confirmed_only:
        conditions.append(Idea.confirmed == ConfirmStatus.APPROVED)
    return (select(Idea)
            .outerjoin(IdeaNote, idea_notes_join(time))
            .outerjoin(IdeaRecognition, IdeaRecognition.idea_id == Idea.id)
            .where(*conditions)
            .distinct()
            .order_by(Idea.id))


def unconfirmed_ideas_select() -> Select:
    """まだ確かめていない候補(`confirmed=未確認`)。退けた(非承認)ものは含めない。"""
    return select(Idea).where(Idea.confirmed == ConfirmStatus.PENDING).order_by(Idea.id)


def ideas_by_parent_select(parent_ids, place_ids=None, time: Stamp | None = None,
                           confirmed_only: bool = True) -> Select:
    conditions = [Idea.parent_idea_id.in_(list(parent_ids)), idea_in_scope(place_ids, time)]
    if confirmed_only:
        conditions.append(Idea.confirmed == ConfirmStatus.APPROVED)
    return select(Idea).where(*conditions).order_by(Idea.id)


def later_ideas_select(place_ids, time: Stamp) -> Select:
    """`time` より後に始まる、`place_ids` の場所で効く確定済みのアイデア。"""
    return (select(Idea)
            .where(Idea.location_id.in_(list(place_ids)),
                   Idea.start > time, Idea.confirmed == ConfirmStatus.APPROVED)
            .order_by(Idea.start, Idea.id))
