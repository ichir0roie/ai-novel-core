#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, select


def unseeded_select(model) -> Select:
    return select(model).where(model.meme_seeded.is_(False)).order_by(model.id)
