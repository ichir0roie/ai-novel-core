#!/usr/bin/env python3
"""出来事・話・人物のどれか一件に、その本文が踏まえたアイデアを結ぶ、claude が呼ぶ入口。

    LinkIdeas([40, 41], event_id=12).run()
"""
from __future__ import annotations

from ai.claude_code.interface._base import CommitEntrypoint
from ai.time_keeper import idea_context
from db.schema import Character, Episode, Event, Idea


class LinkIdeas(CommitEntrypoint):
    model = Idea

    def __init__(self, idea_ids, event_id: int | None = None, episode_id: int | None = None,
                 character_id: int | None = None):
        self.idea_ids = [int(id_) for id_ in idea_ids]
        self.owners = {Event: event_id, Episode: episode_id, Character: character_id}

    def execute(self, session) -> dict:
        given = [(model, int(id_)) for model, id_ in self.owners.items() if id_ is not None]
        if len(given) != 1:
            raise ValueError("event_id / episode_id / character_id のどれか一つだけを渡す")
        model, owner_id = given[0]
        self.check_exists(session, model, owner_id, f"{model.__tablename__}_id")
        for idea_id in self.idea_ids:
            self.check_exists(session, Idea, idea_id, "idea_ids")
        record = session.get(model, owner_id)
        added = idea_context.link(session, record, [session.get(Idea, id_) for id_ in self.idea_ids])
        return {f"{model.__tablename__}_id": owner_id, "linked": added}
