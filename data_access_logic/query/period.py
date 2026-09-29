#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import ColumnElement, and_, or_

from db.schema import CharacterPlace, CharacterRelation, Idea, IdeaRecognition, Location, Story
from db.stamp import Stamp

Period = type[CharacterPlace] | type[CharacterRelation] | type[Idea] | type[IdeaRecognition] | type[Location] | type[Story]


def alive_at(model: Period, time: Stamp) -> ColumnElement[bool]:
    """期間(`start` 〜 `end`)に `time` が入る行。空の端は限りが無く、`end` の時刻そのものはもう入らない。"""
    return and_(or_(model.start.is_(None), model.start <= time),
                or_(model.end.is_(None), model.end > time))
