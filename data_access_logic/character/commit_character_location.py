#!/usr/bin/env python3
"""`commit_character` は出自の一件しか書けないので、出自を後から付ける・移った先を足すときに使う。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterLocationCreateForm
from data_access_logic.character.record import CharacterLocationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import world_creation_query
from db.schema import Character, CharacterLocation, Location


class CommitCharacterLocation(CommitEntrypoint):
    model = CharacterLocation

    def __init__(self, character_location: CharacterLocationCreateForm):
        self.character_location = character_location

    def execute(self, s: Session) -> CharacterLocationRecord:
        self.check_exists(s, Character, self.character_location.character_id, "character_id")
        self.check_exists(s, Location, self.character_location.location_id, "location_id")
        location = s.get_one(Location, self.character_location.location_id)
        world_creation_query.check_within_parent_span(
            location, self.character_location.start, self.character_location.end, "character_location")

        record = CharacterLocation()
        self.character_location.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return CharacterLocationRecord.model_validate(record)
