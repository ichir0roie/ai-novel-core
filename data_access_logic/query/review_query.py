#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, or_, select

from db.schema import Base, Episode, TextBase

TODO_MARK = "TODO"


def text_models() -> list[type]:
    """本文を持つテーブル(`TextBase`)すべて"""
    return [mapper.class_ for mapper in Base.registry.mappers
            if issubclass(mapper.class_, TextBase) and mapper.class_ is not TextBase]


def todo_select(model) -> Select:
    return (select(model)
            .where(or_(*(getattr(model, name).contains(TODO_MARK) for name in model.TEXT_COLUMNS)))
            .order_by(model.id))


def written_unsynced_episodes_select() -> Select:
    return (select(Episode)
            .where(Episode.synced.is_(False), Episode.text != "")
            .order_by(Episode.story_id, Episode.start.asc().nulls_last(), Episode.id))
