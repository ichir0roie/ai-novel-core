#!/usr/bin/env python3
"""出来事・話・人物のどれか一件に、その本文が踏まえたアイデアを結ぶ、claude が呼ぶ入口。

    LinkIdeas([40, 41], event_id=12).show()
"""
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code.interface._base import CommitEntrypoint
from data_access_logic.idea.links import link
from db.schema import Character, Episode, Event, Idea


class LinkedIdeas(BaseModel):
    """結んだ先は、渡した一つだけが埋まる。"""

    event_id: int | None = None
    episode_id: int | None = None
    character_id: int | None = None
    # 新しく結んだ件数(既に結んであったものは数えない)
    linked: int


class LinkIdeas(CommitEntrypoint):
    model = Idea

    def __init__(self, idea_ids: list[int], event_id: int | None = None, episode_id: int | None = None,
                 character_id: int | None = None):
        self.idea_ids = idea_ids
        self.event_id = event_id
        self.episode_id = episode_id
        self.character_id = character_id

    def execute(self, session) -> LinkedIdeas:
        owners = [(model, owner_id) for model, owner_id in
                  ((Event, self.event_id), (Episode, self.episode_id), (Character, self.character_id))
                  if owner_id is not None]
        if len(owners) != 1:
            raise ValueError("event_id / episode_id / character_id のどれか一つだけを渡す")
        model, owner_id = owners[0]
        self.check_exists(session, model, owner_id, f"{model.__tablename__}_id")
        for idea_id in self.idea_ids:
            self.check_exists(session, Idea, idea_id, "idea_ids")
        added = link(session, session.get_one(model, owner_id), [session.get_one(Idea, id_) for id_ in self.idea_ids])
        return LinkedIdeas(event_id=self.event_id, episode_id=self.episode_id, character_id=self.character_id,
                           linked=added)
