#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.character.record import GeneratedCharacter
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.flows import character
from db.stamp import Stamp


class GenerateCharacters(Entrypoint):
    def __init__(self, location_ids: list[int], time: Stamp | str, count: tuple[int, int] = (2, 4),
                 person: bool = True, seed: int | None = None, ai: AIClient = ai_client):
        self.location_ids = location_ids
        self.time = time
        self.count = count
        self.person = person
        self.seed = seed
        self.ai = ai

    def result(self) -> list[GeneratedCharacter]:
        return character.generate_characters(self.location_ids, self.time, self.count, self.person, self.seed, self.ai)
