#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, lazyload

from db.schema import Character, Episode, Event, Story


def unseeded_select(model: type[Story] | type[Episode] | type[Character] | type[Event],
                    *texts: InstrumentedAttribute[str] | InstrumentedAttribute[str | None]) -> Select:
    """まだ種を抜き出していない行のうち、元にする列(`texts`)のどれかが空でないもの。
    元の列が空の行は印を付けずに残るので、SQL の側で外さないと抜き出しのたびに読み直す。
    子の表は読まない(人物の selectin の子は抜き出しに要らない)。"""
    return (select(model)
            .options(lazyload("*"))
            .where(model.event_seeded.is_(False),
                   or_(*(func.trim(func.coalesce(text, "")) != "" for text in texts)))
            .order_by(model.id))
