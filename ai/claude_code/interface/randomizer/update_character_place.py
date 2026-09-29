#!/usr/bin/env python3
"""移った日に前の居場所の `end` を下ろすのに使う。"""
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.character.form import CharacterPlaceUpdateForm
from data_access_logic.character.record import CharacterPlaceRecord
from db.schema import Character, CharacterPlace, Location


class UpdateCharacterPlace(CommitDraft):
    model = CharacterPlace

    def __init__(self, place: CharacterPlaceUpdateForm):
        self.place = place

    def execute(self, session) -> CharacterPlaceRecord:
        self.check_exists(session, Character, self.place.character_id, "character_id")
        self.check_exists(session, Location, self.place.location_id, "location_id")
        record = self.get_or_raise(session, self.place.id, "居場所")
        self.place.write_changes_to(record)
        self.finalize(session, record)
        return CharacterPlaceRecord.model_validate(record)
