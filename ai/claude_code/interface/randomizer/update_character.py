#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.character.form import CharacterUpdateForm
from data_access_logic.character.record import CharacterRecord
from db.child_lists import replaced_rows
from db.schema import Character, CharacterHistory, CharacterParameter, CharacterPlace


class UpdateCharacter(CommitDraft):
    model = Character

    def __init__(self, character: CharacterUpdateForm):
        self.character = character

    def execute(self, session) -> CharacterRecord:
        form = self.character
        record = self.get_or_raise(session, form.id, "人物")

        if form.parameters is not None:
            record.parameters = replaced_rows(record.parameters, form.parameters, CharacterParameter)
        if form.places is not None:
            record.places = replaced_rows(record.places, form.places, CharacterPlace)
        if form.histories is not None:
            record.histories = replaced_rows(record.histories, form.histories, CharacterHistory)
        # 誕生・死亡は列を持たず parameters の行で表す(db/schema.py の Character.start / .end)。
        # 空にするときは null を渡すので、値ではなく渡されたかで決める
        if "start" in form.model_fields_set:
            record.start = form.start
        if "end" in form.model_fields_set:
            record.end = form.end
        form.write_changes_to(record)
        self.finalize(session, record)
        return CharacterRecord.model_validate(record)
