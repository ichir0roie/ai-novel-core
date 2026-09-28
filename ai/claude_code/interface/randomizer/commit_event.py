#!/usr/bin/env python3
"""出来事が人物の信念・立場を大きく動かしたときは、その変化は `Character.text`
へ文章として書き込む(`update_character` を使う)。
"""
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from db.schema import Character, Event, EventCharacter, Location
from db.schema_pydantic import to_dict


class CommitEvent(CommitAndRefresh):
    model = Event

    def __init__(self, event: str | dict):
        self.event = event

    def execute(self, session) -> dict:
        data = self.parse(self.event)
        data.pop("id", None)
        character_ids = [int(id_) for id_ in data.pop("character_ids", None) or []]

        self.check_columns(data)
        if not data.get("name"):
            raise ValueError("name は必須")
        if data.get("time") is None:
            raise ValueError("time は必須")

        self.check_exists(session, Event, data.get("parent_event_id"), "parent_event_id")
        self.check_exists(session, Location, data.get("location_id"), "location_id")
        for character_id in character_ids:
            self.check_exists(session, Character, character_id, "character_ids")

        record = Event(**data)
        record.event_characters = [
            EventCharacter(character_id=character_id) for character_id in character_ids]
        session.add(record)
        self.finalize(session, record)
        return {**to_dict(record), "character_ids": character_ids}
