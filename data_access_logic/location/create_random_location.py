#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import RandomDraft
from randomizer.random_location_generator import build_location


class CreateRandomLocation(RandomDraft):
    builder = staticmethod(build_location)
