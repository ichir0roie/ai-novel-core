#!/usr/bin/env python3
"""出来事・話のあとに、住まい・拠点の変わった人物の居場所(`character_location`)を移す。

AI には移動先の候補(`move_destinations`)を渡し、人物ごとの移動先(`CharacterMove`)を返させる。空なら何も変えない。
出来事は記録の段(`event/progress.py`)の出力に、話は本文を確定したあとの段(`episode/moves.py`)の出力に持つ。
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import common_query, world_creation_query
from db.schema import Character, CharacterLocation
from db.stamp import Stamp

logger = logging.getLogger(__name__)


class CharacterMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="住まい・拠点が変わった人物の人物id")
    location_id: int = Field(description="移動先の候補の場所id")


def move_destinations(s: Session, location_id: int, time: Stamp) -> list[LocationMaterial]:
    """その場所から `constants.REACH_LEVELS` 段上までの配下で、その時刻にある場所(その場所自身を除く)。"""
    root_id = common_query.location_up(s, location_id, constants.REACH_LEVELS)
    nearby_ids = set(common_query.descendant_location_ids(s, root_id)) - {location_id}
    locations = s.scalars(
        world_creation_query.alive_locations_select(time, nearby_ids, constants.MOVE_DESTINATION_LIMIT)).all()
    return [LocationMaterial.model_validate(location) for location in locations]


def apply_moves(
    s: Session, moves: list[CharacterMove], characters: list[Character], destinations: list[LocationMaterial], time: Stamp,
) -> list[CharacterMove]:
    """`characters` のうちの人物を、`destinations` のうちの場所へ移す(ほかを指す移動は捨てる)。移した分を返す。
    今の居場所の行は `time` で閉じ、移動先の行を `time` から始める。"""
    by_id = {character.id: character for character in characters}
    destination_by_id = {destination.id: destination for destination in destinations}
    applied = []
    for move in moves:
        character = by_id.get(move.character_id)
        destination = destination_by_id.get(move.location_id)
        if character is None or destination is None:
            continue
        for current in s.scalars(common_query.character_location_select(character.id, time)).all():
            current.end = time
        s.add(CharacterLocation(character_id=character.id, location_id=destination.id, start=time, end=character.end))
        applied.append(move)
        logger.info(f"{time} {character.name}(id={character.id})の居場所を {destination.name}(id={destination.id})へ移した")
    s.flush()
    return applied
