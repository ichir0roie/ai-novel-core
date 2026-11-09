#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.commit_character_motivation import check_span
from data_access_logic.character.form import CharacterMotivationUpdateForm
from data_access_logic.character.record import CharacterMotivationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterMotivation


class UpdateCharacterMotivation(CommitEntrypoint):
    """モチベーションの行を一つ直す。渡した欄だけを直す(`end` は null を渡せば空に戻す)。"""

    def __init__(self, motivation: CharacterMotivationUpdateForm):
        self.motivation = motivation

    def execute(self, s: Session) -> CharacterMotivationRecord:
        form = self.motivation
        self.check_exists(s, Character, form.character_id, "character_id")
        record = common_query.get_row(s, CharacterMotivation, form.id)
        form.write_changes_to(record)
        check_span(record)
        self.finalize(s, record)
        return CharacterMotivationRecord.model_validate(record)
