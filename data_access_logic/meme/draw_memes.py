#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.meme.extractor import draw
from data_access_logic.meme.models import DrawnMeme

__all__ = ["DrawMemes"]


class DrawMemes(SessionEntrypoint):
    def __init__(self, person: bool = True, seed: int | None = None):
        self.person = person
        self.seed = seed

    def execute(self, s: Session) -> list[DrawnMeme]:
        categories = constants.MEME_PERSON_CATEGORIES if self.person else constants.MEME_NON_PERSON_CATEGORIES
        return draw(s, random.Random(self.seed), categories)
