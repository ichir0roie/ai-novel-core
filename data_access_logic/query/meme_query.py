#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, select

from db.schema import Character, Event, Idea, Oracle


def unseeded_select(model: type[Idea] | type[Oracle] | type[Character] | type[Event]) -> Select:
    return select(model).where(model.meme_seeded.is_(False)).order_by(model.id)
