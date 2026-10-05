#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterSkillCreateForm
from data_access_logic.character.record import CharacterSkillRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import replaced_histories
from db.schema import Character, CharacterSkill, CharacterSkillHistory


class CommitCharacterSkill(CommitEntrypoint):
    """人物にスキルを足す。本文は作者だけが読むので、確定のあとに AI を回さない。"""

    def __init__(self, skill: CharacterSkillCreateForm):
        self.skill = skill

    def execute(self, s: Session) -> CharacterSkillRecord:
        form = self.skill
        self.check_knowers(s, form)
        character = common_query.get_row(s, Character, form.character_id)

        record = CharacterSkill()
        form.write_to(record)
        record.histories = replaced_histories([], form.histories, CharacterSkillHistory, owner=character)
        s.add(record)
        self.finalize(s, record)
        return CharacterSkillRecord.model_validate(record)
