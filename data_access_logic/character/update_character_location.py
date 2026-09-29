#!/usr/bin/env python3
"""移った日に前の居場所の `end` を下ろすのに使う。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterLocationUpdateForm
from data_access_logic.character.record import CharacterLocationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterLocation, Location


class UpdateCharacterLocation(CommitEntrypoint):
    model = CharacterLocation

    def __init__(self, character_location: CharacterLocationUpdateForm):
        self.character_location = character_location

    def execute(self, s: Session) -> CharacterLocationRecord:
        self.check_exists(s, Character, self.character_location.character_id, "character_id")
        self.check_exists(s, Location, self.character_location.location_id, "location_id")
        record = common_query.get_row(s, CharacterLocation, self.character_location.id)
        self.character_location.write_changes_to(record)
        self.finalize(s, record)
        return CharacterLocationRecord.model_validate(record)
