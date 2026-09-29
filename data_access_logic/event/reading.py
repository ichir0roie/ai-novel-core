#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable, Collection

from pydantic import Field, computed_field
from sqlalchemy import Select
from sqlalchemy.orm import Session

from data_access_logic.event.record import EventColumns
from data_access_logic.material import Material, Named
from data_access_logic.query import common_query
from db.schema import Event
from db.stamp import Stamp


class _EventCharacter(Material):
    character_id: int
    character: Named | None = None


class EventRowHead(EventColumns):
    location: Named | None = Field(default=None, exclude=True)
    event_characters: list[_EventCharacter] = Field(exclude=True)

    @computed_field
    @property
    def place_name(self) -> str | None:
        return None if self.location is None else self.location.name

    @computed_field
    @property
    def characters(self) -> list[Named]:
        return [Named(id=link.character_id, name=None if link.character is None else link.character.name)
                for link in self.event_characters]


class EventRow(EventRowHead):
    text: str


def event_row(event: Event, text: bool = True) -> EventRowHead:
    return (EventRow if text else EventRowHead).model_validate(event)


def events_at(session: Session, when: Stamp | str, place_ids: Collection[int] | None = None, limit: int | None = None,
              text: bool = True) -> list[EventRowHead]:
    rows = session.scalars(
        common_query.events_at_select(when, place_ids=place_ids, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def events_of(session: Session, select_fn: Callable[..., Select], record_id: int, until: Stamp | str | None = None,
              limit: int | None = 5,
              text: bool = True) -> list[EventRowHead]:
    rows = session.scalars(select_fn(record_id, until=until, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]
