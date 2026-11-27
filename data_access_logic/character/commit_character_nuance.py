#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterNuanceCreateForm
from data_access_logic.character.nuances import check_nuance
from data_access_logic.character.record import CharacterNuanceRecord
from data_access_logic.entrypoint import CommitEntrypoint
from db.schema import Character, CharacterNuance


class CommitCharacterNuance(CommitEntrypoint):
    """人物に癖(場面と振る舞いの組)か思い込みを一つ足す。本人の人物役が、その時刻に効いている行を読んで演じる。"""

    def __init__(self, nuance: CharacterNuanceCreateForm):
        self.nuance = nuance

    def execute(self, s: Session) -> CharacterNuanceRecord:
        form = self.nuance
        self.check_exists(s, Character, form.character_id, "character_id")
        record = CharacterNuance()
        form.write_to(record)
        check_nuance(record)
        s.add(record)
        self.finalize(s, record)
        return CharacterNuanceRecord.model_validate(record)
