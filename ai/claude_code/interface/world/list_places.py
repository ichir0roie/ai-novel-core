#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.world._base import WorldQuery
from data_access_logic.material import Material
from data_access_logic.query import common_query


class PlaceListing(Material):
    id: int
    name: str | None = None
    kind: str | None = None
    parent_id: int | None = None
    sample_region: str | None = None
    sample_culture: str | None = None
    sample_era: str | None = None


class ListPlaces(WorldQuery):
    def __init__(self, kind: str | None = None):
        self.kind = kind

    def select(self):
        return common_query.places_select(kind=self.kind)

    def row(self, row) -> PlaceListing:
        return PlaceListing.model_validate(row)
