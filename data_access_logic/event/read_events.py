#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.event import reading as event_reading
from data_access_logic.query import common_query
from db.stamp import Stamp

_SELECTS = {
    "place_id": common_query.events_of_place_select,
    "character_id": common_query.events_of_character_select,
    "event_id": common_query.events_under_select,
}


class ReadEvents(SessionEntrypoint):
    """場所・人物・出来事の id は別々の表の連番で重なるので、どの表の id かを引数の名前で渡す。"""

    def __init__(self, time: Stamp | str | None = None, place_id: int | None = None, character_id: int | None = None,
                 event_id: int | None = None, limit: int | None = None, until: Stamp | str | None = None):
        keys = {"time": time, "place_id": place_id, "character_id": character_id, "event_id": event_id}
        given = [key for key, value in keys.items() if value is not None]
        if len(given) != 1:
            raise ValueError("time・place_id・character_id・event_id のどれか一つだけを渡す")
        self.key = given[0]
        self.value = keys[self.key]
        self.limit = limit
        self.until = until

    def execute(self, s: Session) -> list[event_reading.EventRowHead]:
        if self.key == "time":
            return event_reading.events_at(s, self.value, limit=self.limit)
        return event_reading.events_of(s, _SELECTS[self.key], self.value, until=self.until, limit=self.limit)
