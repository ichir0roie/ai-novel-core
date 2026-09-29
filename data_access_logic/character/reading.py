#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection
from typing import Any

from pydantic import SerializeAsAny, model_serializer
from sqlalchemy.orm import Session

from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.record import CharacterHead, CharacterRecord
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.event.reading import EventRowHead, events_of
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query
from db.stamp import Stamp


class PlaceAt(Material):
    place_id: int
    place_name: str | None = None
    start: Timestamp | None = None


class CharacterSheet(Material):
    """人物の列に、ある時刻の名字・体格・口調・性格(`parameters_at`)を同じ段に並べて出す。"""

    character: SerializeAsAny[CharacterHead]
    parameters_at: CharacterParameterValues
    place: PlaceAt | None = None
    recent_events: list[SerializeAsAny[EventRowHead]]

    @model_serializer(mode="wrap")
    def _flat(self, handler: Any) -> dict:
        data = handler(self)
        return {**data.pop("character"), **data.pop("parameters_at"), **data}


def residents(session: Session, place_ids: Collection[int], until: Stamp) -> list[int]:
    character_ids = session.scalars(
        common_query.resident_character_ids_select(place_ids, until)).all()
    return [id_ for id_ in character_ids if id_ is not None]


def _place_at(session: Session, character_id: int, until: Stamp) -> PlaceAt | None:
    row = session.scalars(common_query.character_place_select(character_id, until)).first()
    if row is None:
        return None
    return PlaceAt(place_id=row.location_id, place_name=row.place.name if row.place else None, start=row.start)


def character_sheet(session: Session, character_id: int, until: Stamp | str | None = None,
                    count: int = 5, text: bool = True) -> CharacterSheet:
    character = session.scalars(common_query.character_select(character_id)).first()
    if character is None:
        raise UnknownRecordError(f"id={character_id} の character が見つからない")
    at = common_query.span(until)[1] if until is not None else Stamp(99999, 12, 31, 23, 59, 59)

    return CharacterSheet(
        character=(CharacterRecord if text else CharacterHead).model_validate(character),
        # 時刻を渡さないときは、期間を限らない値だけを重ねる
        parameters_at=parameters_at(character, None if until is None else at),
        place=_place_at(session, character_id, at),
        recent_events=events_of(
            session, common_query.events_of_character_select, character_id, until=None if until is None else at,
            limit=count, text=text),
    )
