#!/usr/bin/env python3
"""人物の居場所(`character_location`)を、移動先(`CharacterMove`)のリストで書き換える。

出来事の記録の段(`event/progress.py`)と、話の本文を確定したあとの段(`episode/moves.py`)は、AI に移動先の候補
(`move_destinations`)を渡して、住まい・拠点の変わった人物ごとの移動先を返させる。流れ(`flows/`)は、そのうち
当事者・登場人物と候補に当たる組だけを残し(`allowed_moves`)、`update_locations`(段 `character.steps.move_characters`)で書き換える。
空なら何も変えない。Claude が直に移すときは入口 `character.move_characters.MoveCharacters`。
"""
from __future__ import annotations

import logging
from collections.abc import Collection

from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character.record import CharacterMove
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import common_query, world_creation_query
from db.schema import Character, CharacterLocation, Location
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def move_destinations(s: Session, location_id: int, time: Stamp) -> list[LocationMaterial]:
    """その場所から `constants.REACH_LEVELS` 段上までの配下で、その時刻にある場所(その場所自身を除く)。"""
    root_id = common_query.location_up(s, location_id, constants.REACH_LEVELS)
    nearby_ids = set(common_query.descendant_location_ids(s, root_id)) - {location_id}
    locations = s.scalars(
        world_creation_query.alive_locations_select(time, nearby_ids, constants.MOVE_DESTINATION_LIMIT)).all()
    return [LocationMaterial.model_validate(location) for location in locations]


def allowed_moves(
    moves: list[CharacterMove], character_ids: Collection[int], destination_ids: Collection[int],
) -> list[CharacterMove]:
    """AI の返した移動のうち、渡した人物・移動先の候補に当たるものだけ(一人に一つ。先のものを使う)。"""
    allowed: dict[int, CharacterMove] = {}
    for move in moves:
        if move.character_id in character_ids and move.location_id in destination_ids:
            allowed.setdefault(move.character_id, move)
    return list(allowed.values())


def update_locations(s: Session, moves: list[CharacterMove], time: Stamp) -> list[CharacterMove]:
    """人物ごとに、`time` に続いている居場所の行を `time` で閉じ、移動先の行を `time` から足す(没年があればそこまで)。
    人物・場所が無ければ止める。書き換えた移動を返す。"""
    for move in moves:
        character = common_query.get_row(s, Character, move.character_id)
        location = common_query.get_row(s, Location, move.location_id)
        for current in s.scalars(common_query.character_location_select(character.id, time)).all():
            current.end = time
        s.add(CharacterLocation(character_id=character.id, location_id=location.id, start=time, end=character.end))
        logger.info(f"{time} {character.name}(id={character.id})の居場所を {location.name}(id={location.id})へ移した")
    s.flush()
    return moves
