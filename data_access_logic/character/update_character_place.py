#!/usr/bin/env python3
"""移った日に前の居場所の `end` を下ろすのに使う。"""
from __future__ import annotations

from data_access_logic.character.form import CharacterPlaceUpdateForm
from data_access_logic.character.record import CharacterPlaceRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterPlace, Location


class UpdateCharacterPlace(CommitEntrypoint):
    model = CharacterPlace

    def __init__(self, place: CharacterPlaceUpdateForm):
        self.place = place

    def execute(self, session) -> CharacterPlaceRecord:
        self.check_exists(session, Character, self.place.character_id, "character_id")
        self.check_exists(session, Location, self.place.location_id, "location_id")
        record = common_query.get_row(session, CharacterPlace, self.place.id)
        self.place.write_changes_to(record)
        self.finalize(session, record)
        return CharacterPlaceRecord.model_validate(record)
