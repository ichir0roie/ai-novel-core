#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, or_, select

from db.schema import Base, ContentBase

TODO_MARK = "TODO"


def text_models() -> list[type]:
    """本文の列を持つテーブル(`ContentBase` のうち `TEXT_COLUMNS` のあるもの)すべて"""
    return [mapper.class_ for mapper in Base.registry.mappers
            if issubclass(mapper.class_, ContentBase) and mapper.class_.TEXT_COLUMNS]


def todo_select(model: type[ContentBase]) -> Select:
    return (select(model)
            .where(or_(*(getattr(model, name).contains(TODO_MARK) for name in model.TEXT_COLUMNS)))
            .order_by(model.id))
