#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Collection
from typing import Any

from pydantic import SerializeAsAny, model_serializer
from sqlalchemy.orm import Session

from data_access_logic.character.histories import histories_at
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.record import CharacterHead, CharacterHistoryRow
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.event.reading import EventRowHead, events_of
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query
from db.stamp import Stamp


class LocationAt(Material):
    location_id: int
    location_name: str | None = None
    start: Timestamp | None = None


class CharacterSheet(Material):
    """人物の列に、ある時刻の名字・体格・口調・性格(`parameters_at`)を同じ段に並べて出す。"""

    character: CharacterHead
    parameters_at: CharacterParameterValues
    appearance: str | None = None
    # 人物の芯(経歴・立場・性格の説明)
    text: str | None = None
    meme: str | None = None
    principle: str | None = None
    plot: str | None = None
    # その時刻までに起きた来歴(時刻を渡さなければ、年の決まっていない行も含めてすべて)
    histories: list[CharacterHistoryRow]
    location: LocationAt | None = None
    recent_events: list[SerializeAsAny[EventRowHead]]

    @model_serializer(mode="wrap")
    def _flat(self, handler: Any) -> dict:
        data = handler(self)
        return {**data.pop("character"), **data.pop("parameters_at"), **data}


def residents(s: Session, location_ids: Collection[int], until: Stamp) -> list[int]:
    character_ids = s.scalars(
        common_query.resident_character_ids_select(location_ids, until)).all()
    return [id_ for id_ in character_ids if id_ is not None]


def _location_at(s: Session, character_id: int, until: Stamp) -> LocationAt | None:
    row = s.scalars(common_query.character_location_select(character_id, until)).first()
    if row is None:
        return None
    return LocationAt(location_id=row.location_id, location_name=row.location.name if row.location else None, start=row.start)


def character_sheet(s: Session, character_id: int, until: Stamp | str | None = None,
                    count: int = 5, text: bool = True) -> CharacterSheet:
    character = s.scalars(common_query.character_select(character_id)).first()
    if character is None:
        raise UnknownRecordError(f"id={character_id} の character が見つからない")
    at = common_query.span(until)[1] if until is not None else Stamp(99999, 12, 31, 23, 59, 59)

    return CharacterSheet(
        character=CharacterHead.model_validate(character),
        # 時刻を渡さないときは、生まれたときの値だけを重ねる
        parameters_at=parameters_at(character, None if until is None else at),
        appearance=character.appearance if text else None,
        text=character.text if text else None,
        meme=character.meme if text else None,
        principle=character.principle if text else None,
        plot=character.plot if text else None,
        histories=histories_at(character, None if until is None else at) if text else [],
        location=_location_at(s, character_id, at),
        recent_events=events_of(
            s, common_query.events_of_character_select, character_id, until=None if until is None else at,
            limit=count, text=text),
    )
