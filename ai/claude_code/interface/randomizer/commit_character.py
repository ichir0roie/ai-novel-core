#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.query import world_createion_query
from db.child_lists import load_children
from db.schema import Character, CharacterPlace, Location
from db.schema_pydantic import to_dict


class CommitCharacter(CommitDraft):
    model = Character

    def __init__(self, character: str | dict):
        self.character = character

    def execute(self, session) -> dict:
        data = self.parse(self.character)
        data.pop("id", None)
        place_id = data.pop("place_id", None)
        parameters = data.pop("parameters", [])
        # 誕生・死亡は列を持たず parameters の行で表す(db/schema.py の Character.start / .end)。
        born = data.pop("start", None)
        died = data.pop("end", None)
        self.check_columns(data)

        self.check_exists(session, Location, place_id, "place_id")
        self._check_span(session, place_id, born, died)
        self._check_story(session, place_id)

        record = Character(**data)
        load_children(record, "parameters", parameters)
        if born is not None:
            record.start = born
        if died is not None:
            record.end = died
        session.add(record)
        session.flush()  # CharacterPlace の character_id に使う id を先に確定させる
        if place_id is not None:
            session.add(CharacterPlace(
                character_id=record.id, location_id=place_id, start=born, end=died))
        self.finalize(session, record)
        return to_dict(record)

    @staticmethod
    def _check_span(session, place_id: int | None, born, died) -> None:
        if place_id is None:
            return
        place = session.get(Location, place_id)
        world_createion_query.check_within_parent_span(place, born, died, "character")

    @staticmethod
    def _check_story(session, place_id: int | None) -> None:
        if place_id is None:
            return
        world_createion_query.check_has_story(session, place_id, "character")
