#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.child_lists import load_children
from db.schema import Character
from db.schema_pydantic import to_dict


class UpdateCharacter(CommitDraft):
    model = Character

    def __init__(self, character: str | dict):
        self.character = character

    def execute(self, session) -> dict:
        data = self.parse(self.character)
        character_id = data.pop("id", None)
        if character_id is None:
            raise ValueError("id は必須(直す対象の人物)")
        parameters = data.pop("parameters", None)
        places = data.pop("places", None)
        self.check_columns(data)

        record = session.get(Character, character_id)
        if record is None:
            raise ValueError(f"id={character_id} という人物が見つからない")

        for key, value in data.items():
            setattr(record, key, value)
        if parameters is not None:
            load_children(record, "parameters", parameters)
        if places is not None:
            load_children(record, "places", places)
        self.finalize(session, record)
        return to_dict(record)
