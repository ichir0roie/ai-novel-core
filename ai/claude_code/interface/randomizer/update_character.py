#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.child_lists import load_children
from db.schema import Character


_UNSET = object()


class UpdateCharacter(CommitDraft):
    model = Character

    def __init__(self, character: str | dict):
        self.character = character

    def execute(self, session) -> dict:
        data = self.parse(self.character)
        character_id = self.require_id(data, "直す対象の人物")
        parameters = data.pop("parameters", None)
        places = data.pop("places", None)
        histories = data.pop("histories", None)
        # 誕生・死亡は列を持たず parameters の行で表す(db/schema.py の Character.start / .end)。
        born = data.pop("start", _UNSET)
        died = data.pop("end", _UNSET)
        self.check_columns(data)

        record = self.get_or_raise(session, character_id, "人物")

        if parameters is not None:
            load_children(record, "parameters", parameters)
        if places is not None:
            load_children(record, "places", places)
        if histories is not None:
            load_children(record, "histories", histories)
        if born is not _UNSET:
            record.start = born
        if died is not _UNSET:
            record.end = died
        return self.apply(session, record, data)
