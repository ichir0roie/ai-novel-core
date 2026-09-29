#!/usr/bin/env python3
from __future__ import annotations

import factory

from data_access_logic.location.form import LocationCreateForm


class LocationFactory(factory.Factory):
    class Meta:
        model = LocationCreateForm

    name = factory.Sequence(lambda n: f"仮の土地{n}")
    kind = "大陸"
    text = ""

    parent_id = None
    location_world = None
    location_planet = None
    location_longitude = None
    location_latitude = None
    location_altitude = None
    area = None
    environment = None
    sample_region = None
    sample_culture = None
    sample_era = None
    start = None
    end = None
    active_random_generation = False


def build_location(**overrides) -> LocationCreateForm:
    return LocationFactory.build(**overrides)
