#!/usr/bin/env python3
"""`commit_character` は出自の一件しか書けないので、出自を後から付ける・移った先を足すときに使う。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterPlaceCreateForm
from data_access_logic.character.record import CharacterPlaceRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import world_creation_query
from db.schema import Character, CharacterPlace, Location


class CommitCharacterPlace(CommitEntrypoint):
    model = CharacterPlace

    def __init__(self, place: CharacterPlaceCreateForm):
        self.place = place

    def execute(self, s: Session) -> CharacterPlaceRecord:
        self.check_exists(s, Character, self.place.character_id, "character_id")
        self.check_exists(s, Location, self.place.location_id, "location_id")
        location = s.get_one(Location, self.place.location_id)
        world_creation_query.check_within_parent_span(
            location, self.place.start, self.place.end, "character_place")

        record = CharacterPlace()
        self.place.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return CharacterPlaceRecord.model_validate(record)
