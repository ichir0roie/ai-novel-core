#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterUpdateForm
from data_access_logic.character.record import CharacterRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import replaced_rows
from db.schema import Character, CharacterHistory, CharacterParameter, CharacterLocation


class UpdateCharacter(CommitEntrypoint):
    model = Character

    def __init__(self, character: CharacterUpdateForm):
        self.character = character

    def execute(self, s: Session) -> CharacterRecord:
        form = self.character
        record = common_query.get_row(s, Character, form.id)

        if form.parameters is not None:
            record.parameters = replaced_rows(record.parameters, form.parameters, CharacterParameter)
        if form.locations is not None:
            record.locations = replaced_rows(record.locations, form.locations, CharacterLocation)
        if form.histories is not None:
            record.histories = replaced_rows(record.histories, form.histories, CharacterHistory)
        # 誕生・死亡は列を持たず parameters の行で表す(db/schema.py の Character.start / .end)。
        # 空にするときは null を渡すので、値ではなく渡されたかで決める
        if "start" in form.model_fields_set:
            record.start = form.start
        if "end" in form.model_fields_set:
            record.end = form.end
        form.write_changes_to(record)
        self.finalize(s, record)
        return CharacterRecord.model_validate(record)
