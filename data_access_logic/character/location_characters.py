#!/usr/bin/env python3
"""ある時刻にある場所にいる人物(話の登場人物を選ぶ画面の候補)。
居場所は国・地方のように広めに持つことがあるので、上位の場所にいる人物もその場所にいるとみなす。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import CharacterLocation
from db.stamp import Stamp


def location_character_ids(s: Session, location_id: int, time: Stamp) -> list[int]:
    location_ids = [step.id for step in common_query.location_path(s, location_id)]
    character_ids = s.scalars(select(CharacterLocation.character_id).where(
        CharacterLocation.location_id.in_(location_ids), alive_at(CharacterLocation, time))).all()
    return sorted({character_id for character_id in character_ids if character_id is not None})
