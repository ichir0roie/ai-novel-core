#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterHead
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.event import reading as event_reading
from data_access_logic.material import Timestamp
from data_access_logic.query import character_simulation_query, common_query
from db.stamp import Stamp


class Surroundings(BaseModel):
    character_id: int
    time: Timestamp
    reach: int
    characters: list[CharacterHead]
    events: list[event_reading.EventRow]


class ReadSurroundings(SessionEntrypoint):
    def __init__(self, character_id: int, time: Stamp | str | None, reach: int = 60):
        if time is None:
            raise ValueError("時刻が決まらない(time を渡す)")
        self.character_id = character_id
        self.time = time
        self.reach = reach

    def execute(self, session: Session) -> Surroundings:
        _, until = common_query.span(self.time)
        characters, events = character_simulation_query.character_around_event(
            session, self.character_id, until, reach=self.reach)
        return Surroundings(
            character_id=self.character_id, time=until, reach=self.reach,
            characters=[CharacterHead.model_validate(character) for character in characters],
            events=[event_reading.EventRow.model_validate(event) for event in events])
