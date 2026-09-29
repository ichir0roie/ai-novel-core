#!/usr/bin/env python3
from __future__ import annotations

import random

from ai.claude_code.interface._base import SessionEntrypoint
from ai.time_keeper import constants
from data_access_logic.meme.extractor import draw
from data_access_logic.meme.models import DrawnMeme

__all__ = ["DrawMemes"]


class DrawMemes(SessionEntrypoint):
    def __init__(self, person: bool = True, seed: int | None = None):
        self.person = person
        self.seed = seed

    def execute(self, session) -> list[DrawnMeme]:
        categories = constants.MEME_PERSON_CATEGORIES if self.person else constants.MEME_NON_PERSON_CATEGORIES
        return draw(session, random.Random(self.seed), categories)
