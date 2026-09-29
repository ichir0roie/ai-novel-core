#!/usr/bin/env python3
"""ある時刻にある場所にいる人物。話の登場人物を選ぶ画面が、候補を話の場所・時刻で絞るのに使う。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query.period import alive_at
from db.schema import CharacterPlace
from db.stamp import Stamp


def place_character_ids(s: Session, place_id: int, time: Stamp) -> list[int]:
    places = s.scalars(select(CharacterPlace)
                       .where(CharacterPlace.location_id == place_id, alive_at(CharacterPlace, time))).all()
    return sorted({place.character_id for place in places if place.character_id is not None})
