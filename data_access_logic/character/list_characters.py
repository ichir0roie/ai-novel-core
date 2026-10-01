#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select

from data_access_logic.character.histories import histories_at
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.entrypoint import ListEntrypoint
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import Character


class CharacterListing(Material):
    id: int
    name: str | None = None
    family_name: str | None = None
    kind: str
    # 説明・来歴のすべての行(始まりの古い順)
    histories: list[CharacterHistoryRow]
    sex: str | None = None
    tone: str | None = None
    dialect: str | None = None
    # 一番新しく移った先(`locations` は start の新しい順)
    location_id: int | None = None


class ListCharacters(ListEntrypoint):
    def select(self) -> Select:
        return common_query.characters_select()

    def row(self, row: Character) -> CharacterListing:
        parameters = parameters_at(row, None)
        return CharacterListing(
            id=row.id, name=row.name, family_name=parameters.family_name, kind=row.kind,
            histories=histories_at(row, None),
            sex=parameters.sex, tone=parameters.tone, dialect=parameters.dialect,
            location_id=row.locations[0].location_id if row.locations else None)
