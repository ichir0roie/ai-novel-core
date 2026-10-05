#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterSkillUpdateForm
from data_access_logic.character.record import CharacterSkillRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import replaced_histories
from db.schema import Character, CharacterSkill, CharacterSkillHistory


class UpdateCharacterSkill(CommitEntrypoint):

    def __init__(self, skill: CharacterSkillUpdateForm):
        self.skill = skill

    def execute(self, s: Session) -> CharacterSkillRecord:
        form = self.skill
        self.check_knowers(s, form)
        self.check_exists(s, Character, form.character_id, "character_id")
        record = common_query.get_row(s, CharacterSkill, form.id)

        form.write_changes_to(record)
        if form.histories is not None:
            character = common_query.get_row(s, Character, record.character_id)
            record.histories = replaced_histories(record.histories, form.histories, CharacterSkillHistory,
                                                  owner=character)
        self.finalize(s, record)
        return CharacterSkillRecord.model_validate(record)
