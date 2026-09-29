#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import RandomDraft
from data_access_logic.character.form import CharacterCreateForm
from randomizer.random_character_generator import build_character


class CreateRandomCharacter(RandomDraft):
    builder = staticmethod(build_character)
    draft_model = CharacterCreateForm
