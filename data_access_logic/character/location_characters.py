#!/usr/bin/env python3
"""ある時刻にある場所にいる人物。話の登場人物を選ぶ画面が、候補を話の場所・時刻で絞るのに使う。

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
    character_locations = s.scalars(select(CharacterLocation)
                       .where(CharacterLocation.location_id.in_(location_ids), alive_at(CharacterLocation, time))).all()
    return sorted({character_location.character_id for character_location in character_locations if character_location.character_id is not None})
