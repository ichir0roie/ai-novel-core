#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.world._base import WorldQuery
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import Character


class CharacterListing(Material):
    id: int
    name: str | None = None
    family_name: str | None = None
    kind: str
    text: str | None = None
    sex: str | None = None
    tone: str | None = None
    dialect: str | None = None
    # 一番新しく移った先(`places` は start の新しい順)
    place_id: int | None = None


class ListCharacters(WorldQuery):
    def select(self):
        return common_query.characters_select()

    def row(self, row: Character) -> CharacterListing:
        parameters = CharacterParameterValues.model_validate(row.parameters_at())
        return CharacterListing(
            id=row.id, name=row.name, family_name=parameters.family_name, kind=row.kind, text=row.text,
            sex=parameters.sex, tone=parameters.tone, dialect=parameters.dialect,
            place_id=row.places[0].location_id if row.places else None)
