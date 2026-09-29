#!/usr/bin/env python3
"""`commit_character` は出自の一件しか書けないので、出自を後から付ける・移った先を足すときに使う。"""
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.character.form import CharacterPlaceCreateForm
from data_access_logic.character.record import CharacterPlaceRecord
from data_access_logic.query import world_createion_query
from db.schema import Character, CharacterPlace, Location


class CommitCharacterPlace(CommitDraft):
    model = CharacterPlace

    def __init__(self, place: CharacterPlaceCreateForm):
        self.place = place

    def execute(self, session) -> CharacterPlaceRecord:
        self.check_exists(session, Character, self.place.character_id, "character_id")
        self.check_exists(session, Location, self.place.location_id, "location_id")
        location = session.get_one(Location, self.place.location_id)
        world_createion_query.check_within_parent_span(
            location, self.place.start, self.place.end, "character_place")

        record = CharacterPlace(**self.place.column_values(CharacterPlace))
        session.add(record)
        self.finalize(session, record)
        return CharacterPlaceRecord.model_validate(record)
