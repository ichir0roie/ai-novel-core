#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from data_access_logic.character.record import CharacterHead
from data_access_logic.material import Timestamp
from data_access_logic.query import character_simulation_query, common_query


class Surroundings(BaseModel):
    character_id: int
    time: Timestamp
    reach: int
    characters: list[CharacterHead]
    events: list[_rows.EventRow]


class ReadSurroundings(StoryQuery):
    def __init__(self, character_id: int, time, reach: int = 60):
        if time is None:
            raise ValueError("時刻が決まらない(time を渡す)")
        self.character_id = character_id
        self.time = time
        self.reach = reach

    def execute(self, session) -> Surroundings:
        _, until = common_query.span(self.time)
        characters, events = character_simulation_query.character_around_event(
            session, self.character_id, until, reach=self.reach)
        return Surroundings(
            character_id=self.character_id, time=until, reach=self.reach,
            characters=[CharacterHead.model_validate(character) for character in characters],
            events=[_rows.EventRow.model_validate(event) for event in events])
