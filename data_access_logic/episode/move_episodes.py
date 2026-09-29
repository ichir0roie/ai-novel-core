#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode.record import EpisodeHead
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeSummary, Story


class MoveEpisodes(CommitEntrypoint):
    model = Episode

    def __init__(self, episode_ids: list[int], story_id: int):
        self.episode_ids = episode_ids
        self.story_id = story_id

    def execute(self, s: Session) -> list[EpisodeHead]:
        common_query.get_row(s, Story, self.story_id)
        for episode_id in self.episode_ids:
            common_query.get_row(s, Episode, episode_id)
        # 本文も枠も変わらないので、同期フラグと要約はそのまま残し、要約の作品だけを付け替える
        s.execute(update(Episode).where(Episode.id.in_(self.episode_ids)).values(story_id=self.story_id))
        s.execute(update(EpisodeSummary).where(EpisodeSummary.episode_id.in_(self.episode_ids))
                  .values(story_id=self.story_id))
        rows = s.scalars(select(Episode).where(Episode.id.in_(self.episode_ids))
                         .order_by(*common_query.episode_order())
                         .execution_options(populate_existing=True)).all()
        return [EpisodeHead.model_validate(row) for row in rows]
