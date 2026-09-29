#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import RandomDraft
from randomizer.random_character_generator import build_character


class CreateRandomCharacter(RandomDraft):
    builder = staticmethod(build_character)
