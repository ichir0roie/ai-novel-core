#!/usr/bin/env python3
from __future__ import annotations

from pydantic import Field, computed_field
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import record_of
from data_access_logic.episode.record import EpisodeHead, EpisodeRecord, EpisodeRow
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


def episodes(s: Session, story_id: int, count: int = 10, before: Stamp | str | None = None,
             text: bool = True) -> list[EpisodeHead]:
    common_query.get_row(s, Story, story_id)
    rows = s.scalars(
        common_query.episodes_select(story_id, count=count, before=before)).all()
    return [(EpisodeRow if text else EpisodeHead).model_validate(episode) for episode in reversed(rows)]


def last_episode(s: Session, story_id: int) -> EpisodeRecord | None:
    """作品の中の並び(`common_query.episode_order`)で一番後ろの話。新しい話の場所・視点・登場人物の初期値にする。"""
    row = s.scalars(common_query.episodes_select(story_id, count=1)).first()
    return None if row is None else record_of(s, EpisodeRecord, row)


def unsynced_episodes(s: Session, story_id: int | None = None) -> list[UnsyncedEpisode]:
    rows = s.scalars(common_query.unsynced_episodes_select(story_id)).all()
    return [UnsyncedEpisode.model_validate(episode) for episode in rows]
