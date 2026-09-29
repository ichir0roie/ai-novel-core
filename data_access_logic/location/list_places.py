#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select

from data_access_logic.entrypoint import ListEntrypoint
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import Location


class PlaceListing(Material):
    id: int
    name: str | None = None
    kind: str | None = None
    parent_id: int | None = None
    sample_region: str | None = None
    sample_culture: str | None = None
    sample_era: str | None = None


class ListPlaces(ListEntrypoint):
    def __init__(self, kind: str | None = None):
        self.kind = kind

    def select(self) -> Select:
        return common_query.places_select(kind=self.kind)

    def row(self, row: Location) -> PlaceListing:
        return PlaceListing.model_validate(row)
