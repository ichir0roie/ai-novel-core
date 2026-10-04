#!/usr/bin/env python3
from __future__ import annotations

import logging
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator import birth_sources, generate_character, story_elements
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query, world_creation_query
from db.schema import Location, Stamp

logger = logging.getLogger(__name__)


def check_locations(s: Session, location_ids: list[int]) -> None:
    for location_id in location_ids:
        if s.get(Location, location_id) is None:
            raise ValueError(f"location_id={location_id} という id の location が見つからない")
        world_creation_query.check_has_story(s, location_id, "character")


def resident_rooms(s: Session, location_ids: list[int], time: Stamp) -> dict[int, int]:
    """場所ごとに、上限(`constants.RESIDENT_LIMITS`)まであと何人足せるか。"""
    rooms = {}
    for location_id in location_ids:
        location = common_query.get_row(s, Location, location_id)
        limit = constants.RESIDENT_LIMITS.get(location.kind or "", constants.DEFAULT_RESIDENT_LIMIT)
        residents = s.scalar(select(func.count()).select_from(
            common_query.resident_character_ids_select([location_id], time).subquery())) or 0
        rooms[location_id] = max(0, limit - residents)
    return rooms


def capped_count(rng: random.Random, count: tuple[int, int], location_id: int, room: int) -> int:
    wanted = rng.randint(*count)
    if wanted > room:
        logger.warning(f"location_id={location_id} は人数の上限まであと {room} 人なので、{wanted} 人でなく {room} 人だけ足す")
    return min(wanted, room)


class GenerateCharacters(SessionEntrypoint):
    def __init__(self, location_ids: list[int], time: Stamp | str, count: tuple[int, int] = (2, 4),
                 person: bool = True, seed: int | None = None, ai: AIClient = ai_client):
        self.location_ids = location_ids
        self.time = Stamp.parse(time)
        self.count = count
        self.person = person
        self.seed = seed
        self.ai = ai

    def execute(self, s: Session) -> list[GeneratedCharacter]:
        check_locations(s, self.location_ids)
        rooms = resident_rooms(s, self.location_ids, self.time)
        rng = random.Random(self.seed)
        created = []
        # generate_character は一人ごとに commit するので、途中で止まっても作った人物は残る
        for location_id in self.location_ids:
            count = capped_count(rng, self.count, location_id, rooms[location_id])
            if not count:
                continue
            # 筋書きの立場は同じ場所・時刻なら変わらないので、場所ごとに一度だけ抜き出して一人ずつサイコロで選ぶ
            elements = story_elements(self.ai, birth_sources(s, location_id, self.time, self.person), self.time)
            for _ in range(count):
                record = generate_character(s, self.ai, rng, location_id, self.time, self.person, elements=elements)
                if record is not None:
                    created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=location_id))
        return created
