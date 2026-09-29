#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, select

from db.schema import Character, Episode, Event, Story


def unseeded_select(model: type[Story] | type[Episode] | type[Character] | type[Event]) -> Select:
    return (select(model)
            .where(model.event_seeded.is_(False))
            .order_by(model.id))
