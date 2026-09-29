from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import Character, CharacterPlace, ConfirmStatus, Event, Location
from db.stamp import Stamp


def character_around_event(
    s: Session, character_id: int, time: Stamp, reach: int = 60,
) -> tuple[Sequence[Character], Sequence[Event]]:
    """話の材料(周りの人物・出来事)なので、ユーザが確かめた(`confirmed=承認`)ものだけに絞る。"""
    character_location_ids = select(CharacterPlace.location_id).where(
        CharacterPlace.character_id == character_id, alive_at(CharacterPlace, time))

    parent_locations = s.scalars(
        select(Location)
        .where(or_(Location.parent_id.in_(character_location_ids),
                   Location.id.in_(character_location_ids)))
        .options(selectinload(Location.children))
    ).all()
    location_ids = [location.id for parent in parent_locations
                    for location in (parent, *parent.children)]

    characters = s.scalars(
        select(Character).join(CharacterPlace, and_(
            CharacterPlace.character_id == Character.id,
            CharacterPlace.location_id.in_(location_ids),
            alive_at(CharacterPlace, time)))
        .where(Character.confirmed == ConfirmStatus.APPROVED)
    ).all()
    since = Stamp(max(1, time.year - reach))
    events = s.scalars(
        select(Event)
        .options(*common_query.EVENT_LOAD_OPTIONS)
        .where(Event.location_id.in_(location_ids), Event.time <= time, Event.time >= since,
               Event.confirmed == ConfirmStatus.APPROVED)
        .order_by(Event.time.desc(), Event.id.desc())
    ).all()

    return characters, events
