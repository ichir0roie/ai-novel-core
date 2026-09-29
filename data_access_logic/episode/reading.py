#!/usr/bin/env python3
from __future__ import annotations

from pydantic import Field, computed_field
from sqlalchemy.orm import Session

from data_access_logic.episode.record import EpisodeHead, EpisodeRow
from data_access_logic.material import Material, Named, Timestamp
from data_access_logic.query import common_query
from db.schema import Story
from db.stamp import Stamp


class EpisodeTitle(Material):
    id: int
    start: Timestamp | None = None
    title: str


class UnsyncedEpisode(EpisodeTitle):
    story_id: int
    story: Named | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def story_name(self) -> str | None:
        return None if self.story is None else self.story.name


def episodes(session: Session, story_id: int, count: int = 10, before: Stamp | str | None = None,
             text: bool = True) -> list[EpisodeHead]:
    common_query.get_row(session, Story, story_id)
    rows = session.scalars(
        common_query.episodes_select(story_id, count=count, before=before)).all()
    return [(EpisodeRow if text else EpisodeHead).model_validate(episode) for episode in reversed(rows)]


def unsynced_episodes(session: Session, story_id: int | None = None) -> list[UnsyncedEpisode]:
    rows = session.scalars(common_query.unsynced_episodes_select(story_id)).all()
    return [UnsyncedEpisode.model_validate(episode) for episode in rows]
