#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, or_, select

from db.schema import Base, Episode, EpisodeText, MarkdownBase

TODO_MARK = "TODO"


def markdown_models() -> list[type]:
    return [mapper.class_ for mapper in Base.registry.mappers
            if issubclass(mapper.class_, MarkdownBase) and mapper.class_ is not MarkdownBase]


def todo_select(model) -> Select:
    return (select(model)
            .where(or_(*(getattr(model, name).contains(TODO_MARK) for name in model.TEXT_SECTIONS)))
            .order_by(model.id))


def written_unsynced_episodes_select() -> Select:
    return (select(Episode)
            .join(EpisodeText, EpisodeText.episode_id == Episode.id)
            .where(Episode.synced.is_(False), EpisodeText.text != "")
            .order_by(Episode.story_id, Episode.start.asc().nulls_last(), Episode.id))
