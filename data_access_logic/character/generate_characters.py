#!/usr/bin/env python3
from __future__ import annotations

import random

from ai.claude_code import ai_client
from data_access_logic.character.generator import generate_character
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import world_createion_query
from db.schema import Location, Stamp


class GenerateCharacters(SessionEntrypoint):
    def __init__(self, place_ids: list[int], time, count: tuple[int, int] = (2, 4),
                 person: bool = True, seed: int | None = None, ai=ai_client):
        self.place_ids = place_ids
        self.time = Stamp.parse(time)
        self.count = count
        self.person = person
        self.seed = seed
        self.ai = ai

    def execute(self, session) -> list[GeneratedCharacter]:
        places = []
        for place_id in self.place_ids:
            place = session.get(Location, place_id)
            if place is None:
                raise ValueError(f"place_id={place_id} という id の location が見つからない")
            world_createion_query.check_has_story(session, place_id, "character")
            places.append(place)

        rng = random.Random(self.seed)
        created = []
        # generate_character は一人ごとに commit するので、途中で止まっても作った人物は残る
        for place in places:
            for _ in range(rng.randint(*self.count)):
                record = generate_character(session, self.ai, rng, place.id, self.time, self.person)
                if record is not None:
                    created.append(GeneratedCharacter(id=record.id, name=record.name, place_id=place.id))
        return created
