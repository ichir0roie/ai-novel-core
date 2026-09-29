#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.character.form import CharacterUpdateForm
from data_access_logic.character.record import CharacterRecord
from db.child_lists import load_children
from db.schema import Character


class UpdateCharacter(CommitDraft):
    model = Character

    def __init__(self, character: CharacterUpdateForm):
        self.character = character

    def execute(self, session) -> CharacterRecord:
        form = self.character
        record = self.get_or_raise(session, form.id, "人物")

        if form.parameters is not None:
            load_children(record, "parameters", [row.model_dump() for row in form.parameters])
        if form.places is not None:
            load_children(record, "places", [row.model_dump() for row in form.places])
        if form.histories is not None:
            load_children(record, "histories", [row.model_dump() for row in form.histories])
        # 誕生・死亡は列を持たず parameters の行で表す(db/schema.py の Character.start / .end)。
        # 空にするときは null を渡すので、値ではなく渡されたかで決める
        if "start" in form.model_fields_set:
            record.start = form.start
        if "end" in form.model_fields_set:
            record.end = form.end
        self.apply(session, record, form.changed_column_values(Character))
        return CharacterRecord.model_validate(record)
