#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, select

from db.schema import Meme


def unseeded_select(model) -> Select:
    return select(model).where(model.meme_seeded.is_(False)).order_by(model.id)


def unconfirmed_memes_select() -> Select:
    return select(Meme).where(Meme.confirmed.is_(False)).order_by(Meme.id)
