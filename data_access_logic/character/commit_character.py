#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterCreateForm
from data_access_logic.character.record import CharacterRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import world_creation_query
from db.child_lists import replaced_histories, replaced_rows
from db.schema import Character, CharacterHistory, CharacterKnower, CharacterParameter, CharacterLocation, Location


class CommitCharacter(CommitEntrypoint):
    model = Character

    def __init__(self, character: CharacterCreateForm):
        self.character = character

    def execute(self, s: Session) -> CharacterRecord:
        form = self.character
        self.check_knowers(s, form)
        self.check_exists(s, Location, form.location_id, "location_id")
        if form.location_id is not None:
            location = s.get_one(Location, form.location_id)
            world_creation_query.check_within_parent_span(location, form.start, form.end, "character")
            world_creation_query.check_has_story(s, form.location_id, "character")

        record = Character()
        form.write_to(record)
        record.parameters = replaced_rows([], form.parameters, CharacterParameter)
        record.histories = replaced_histories([], form.histories, CharacterHistory, owner=record)
        # 本人は作るときに知る相手に入っている(`db/schema.py` の `_knows_oneself`)
        record.knowers = [*record.knowers, *replaced_rows([], form.knowers, CharacterKnower)]
        # 誕生は列を持たず parameters の一番早く始まる行の start で表す(db/schema.py の Character.start)。
        if form.start is not None:
            record.start = form.start
        s.add(record)
        s.flush()  # CharacterLocation の character_id に使う id を先に確定させる
        if form.location_id is not None:
            s.add(CharacterLocation(
                character_id=record.id, location_id=form.location_id, start=form.start, end=form.end))
        self.finalize(s, record)
        return CharacterRecord.model_validate(record)
