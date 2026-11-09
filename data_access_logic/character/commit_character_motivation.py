#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterMotivationCreateForm
from data_access_logic.character.record import CharacterMotivationRecord
from data_access_logic.entrypoint import CommitEntrypoint
from db.schema import Character, CharacterMotivation


def check_span(record: CharacterMotivation) -> None:
    if record.end is not None and record.end <= record.start:
        raise ValueError(f"end({record.end})は start({record.start})より後にする")


class CommitCharacterMotivation(CommitEntrypoint):
    """人物にモチベーション(いま何をしたがっているか)を一つ足す。人物モードの人物の目が、その時刻に効いている行を読む。"""

    def __init__(self, motivation: CharacterMotivationCreateForm):
        self.motivation = motivation

    def execute(self, s: Session) -> CharacterMotivationRecord:
        form = self.motivation
        self.check_exists(s, Character, form.character_id, "character_id")
        record = CharacterMotivation()
        form.write_to(record)
        check_span(record)
        s.add(record)
        self.finalize(s, record)
        return CharacterMotivationRecord.model_validate(record)
