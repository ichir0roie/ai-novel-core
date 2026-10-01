#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, or_, select

from db.schema import Base, Character, ConfirmStatus, ContentBase, Episode, Event, Idea, Meme

TODO_MARK = "TODO"


def pending_select(model: type[Character] | type[Event] | type[Idea] | type[Meme]) -> Select:
    """まだ確かめていない候補(`confirmed=未確認`)。退けた(非承認)ものは含めない。"""
    return select(model).where(model.confirmed == ConfirmStatus.PENDING).order_by(model.id)


def text_models() -> list[type]:
    """本文の列を持つテーブル(`ContentBase` のうち `TEXT_COLUMNS` のあるもの)すべて"""
    return [mapper.class_ for mapper in Base.registry.mappers
            if issubclass(mapper.class_, ContentBase) and mapper.class_.TEXT_COLUMNS]


def todo_select(model: type[ContentBase]) -> Select:
    return (select(model)
            .where(or_(*(getattr(model, name).contains(TODO_MARK) for name in model.TEXT_COLUMNS)))
            .order_by(model.id))


def written_unsynced_episodes_select() -> Select:
    return (select(Episode)
            .where(Episode.synced.is_(False), Episode.main_text != "")
            .order_by(Episode.story_id, Episode.start.asc().nulls_last(), Episode.id))
