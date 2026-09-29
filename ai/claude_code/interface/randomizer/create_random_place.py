#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import RandomDraft
from data_access_logic.location.form import LocationCreateForm
from randomizer.random_location_generator import build_location


class CreateRandomPlace(RandomDraft):
    builder = staticmethod(build_location)
    draft_model = LocationCreateForm
