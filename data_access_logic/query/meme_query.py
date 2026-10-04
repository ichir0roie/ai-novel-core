#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, select

from db.schema import Episode, Event, Oracle


def unseeded_select(model: type[Oracle] | type[Event] | type[Episode]) -> Select:
    return select(model).where(model.meme_seeded.is_(False)).order_by(model.id)
