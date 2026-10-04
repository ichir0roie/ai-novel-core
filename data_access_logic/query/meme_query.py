#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import InstrumentedAttribute

from db.schema import Episode, Event, Oracle


def unseeded_select(model: type[Oracle] | type[Event] | type[Episode], text: InstrumentedAttribute[str]) -> Select:
    """まだミームを抜き出していない行のうち、元にする列(`text`)が空でないもの。
    元の列が空の行は印を付けずに残るので、SQL の側で外さないと抜き出しのたびに読み直す。"""
    return (select(model)
            .where(model.meme_seeded.is_(False), func.trim(func.coalesce(text, "")) != "")
            .order_by(model.id))
