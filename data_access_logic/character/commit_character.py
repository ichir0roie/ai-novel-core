#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.character.form import CharacterCreateForm
from data_access_logic.character.record import CharacterRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import world_creation_query
from db.child_lists import replaced_rows
from db.schema import Character, CharacterHistory, CharacterParameter, CharacterPlace, Location


class CommitCharacter(CommitEntrypoint):
    model = Character

    def __init__(self, character: CharacterCreateForm):
        self.character = character

    def execute(self, session) -> CharacterRecord:
        form = self.character
        self.check_exists(session, Location, form.place_id, "place_id")
        if form.place_id is not None:
            place = session.get_one(Location, form.place_id)
            world_creation_query.check_within_parent_span(place, form.start, form.end, "character")
            world_creation_query.check_has_story(session, form.place_id, "character")

        record = Character()
        form.write_to(record)
        record.parameters = replaced_rows([], form.parameters, CharacterParameter)
        record.histories = replaced_rows([], form.histories, CharacterHistory)
        # 誕生・死亡は列を持たず parameters の行で表す(db/schema.py の Character.start / .end)。
        if form.start is not None:
            record.start = form.start
        if form.end is not None:
            record.end = form.end
        session.add(record)
        session.flush()  # CharacterPlace の character_id に使う id を先に確定させる
        if form.place_id is not None:
            session.add(CharacterPlace(
                character_id=record.id, location_id=form.place_id, start=form.start, end=form.end))
        self.finalize(session, record)
        return CharacterRecord.model_validate(record)
