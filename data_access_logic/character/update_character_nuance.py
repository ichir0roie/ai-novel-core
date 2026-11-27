#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterNuanceUpdateForm
from data_access_logic.character.nuances import check_nuance
from data_access_logic.character.record import CharacterNuanceRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterNuance


class UpdateCharacterNuance(CommitEntrypoint):
    """癖・思い込みの行を一つ直す。渡した欄だけを直す(`situation`・`start`・`end` は null を渡せば空に戻す)。"""

    def __init__(self, nuance: CharacterNuanceUpdateForm):
        self.nuance = nuance

    def execute(self, s: Session) -> CharacterNuanceRecord:
        form = self.nuance
        record = common_query.get_row(s, CharacterNuance, form.id)
        form.write_changes_to(record)
        check_nuance(record)
        self.finalize(s, record)
        return CharacterNuanceRecord.model_validate(record)
