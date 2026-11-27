#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select

from data_access_logic.character.nuances import nuances_select
from data_access_logic.character.record import CharacterNuanceRecord
from data_access_logic.entrypoint import ListEntrypoint
from db.schema import CharacterNuance
from db.stamp import Stamp


class ListCharacterNuances(ListEntrypoint):
    """人物の癖と思い込み。`time` を渡せばその時刻に効いている行を、省けばすべての行を、癖 → 思い込みの順に返す。"""

    def __init__(self, character_id: int, time: Stamp | str | None = None):
        self.character_id = character_id
        self.time = time

    def select(self) -> Select:
        return nuances_select(self.character_id, Stamp.parse(self.time))

    def row(self, row: CharacterNuance) -> CharacterNuanceRecord:
        return CharacterNuanceRecord.model_validate(row)
