#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import ColumnElement, and_, or_

from db.schema import CharacterLocation, CharacterRelation, Idea, IdeaHistory, Location
from db.stamp import Stamp

Period = type[CharacterLocation] | type[CharacterRelation] | type[Idea] | type[IdeaHistory] | type[Location]


def alive_at(model: Period, time: Stamp) -> ColumnElement[bool]:
    """期間(`start` 〜 `end`)に `time` が入る行。空の端は限りが無く、`end` の時刻そのものはもう入らない。"""
    return and_(or_(model.start.is_(None), model.start <= time),
                or_(model.end.is_(None), model.end > time))


def dated_alive_at(model: Period, time: Stamp) -> ColumnElement[bool]:
    """`alive_at` のうち、始まりの決まった行。人物役・語り部が読む行は、いつからか決まっていないものを読ませない。"""
    return and_(model.start.is_not(None), alive_at(model, time))
