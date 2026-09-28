#!/usr/bin/env python3
"""移った日に前の居場所の `end` を下ろすのに使う。"""
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import Character, CharacterPlace, Location


class UpdateCharacterPlace(CommitDraft):
    model = CharacterPlace

    def __init__(self, place: str | dict):
        self.place = place

    def execute(self, session) -> dict:
        data = self.parse(self.place)
        place_id = self.require_id(data, "直す対象の居場所")
        self.check_columns(data)
        self.check_exists(session, Character, data.get("character_id"), "character_id")
        self.check_exists(session, Location, data.get("location_id"), "location_id")

        record = self.get_or_raise(session, place_id, "居場所")

        return self.apply(session, record, data)
