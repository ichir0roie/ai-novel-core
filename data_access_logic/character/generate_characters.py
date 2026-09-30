#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator import generate_character
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import world_creation_query
from db.schema import Location, Stamp


def check_locations(s: Session, location_ids: list[int]) -> None:
    for location_id in location_ids:
        if s.get(Location, location_id) is None:
            raise ValueError(f"location_id={location_id} という id の location が見つからない")
        world_creation_query.check_has_story(s, location_id, "character")


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
        rng = random.Random(self.seed)
        created = []
        # generate_character は一人ごとに commit するので、途中で止まっても作った人物は残る
        for location_id in self.location_ids:
            for _ in range(rng.randint(*self.count)):
                record = generate_character(s, self.ai, rng, location_id, self.time, self.person)
                if record is not None:
                    created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=location_id))
        return created
