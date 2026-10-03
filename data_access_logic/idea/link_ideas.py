#!/usr/bin/env python3
"""話に、その本文が踏まえたアイデアを結ぶ、claude が呼ぶ入口。

    LinkIdeas([40, 41], episode_id=12).show()
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.links import link
from db.schema import Episode, Idea


class LinkedIdeas(BaseModel):
    episode_id: int
    # 新しく結んだ件数(既に結んであったものは数えない)
    linked: int


class LinkIdeas(CommitEntrypoint):
    model = Idea

    def __init__(self, idea_ids: list[int], episode_id: int):
        self.idea_ids = idea_ids
        self.episode_id = episode_id

    def execute(self, s: Session) -> LinkedIdeas:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        for idea_id in self.idea_ids:
            self.check_exists(s, Idea, idea_id, "idea_ids")
        added = link(s, s.get_one(Episode, self.episode_id), [s.get_one(Idea, id_) for id_ in self.idea_ids])
        return LinkedIdeas(episode_id=self.episode_id, linked=added)
