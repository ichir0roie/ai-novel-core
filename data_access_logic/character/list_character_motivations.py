#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select

from data_access_logic.character.motivations import motivations_select
from data_access_logic.character.record import CharacterMotivationRecord
from data_access_logic.entrypoint import ListEntrypoint
from db.schema import CharacterMotivation
from db.stamp import Stamp


class ListCharacterMotivations(ListEntrypoint):
    """人物のモチベーション。`time` を渡せばその時刻に効いている行を強い順に、省けばすべての行を始まりの新しい順に返す。"""

    def __init__(self, character_id: int, time: Stamp | str | None = None):
        self.character_id = character_id
        self.time = time

    def select(self) -> Select:
        return motivations_select([self.character_id], Stamp.parse(self.time))

    def row(self, row: CharacterMotivation) -> CharacterMotivationRecord:
        return CharacterMotivationRecord.model_validate(row)
