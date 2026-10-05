#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterSkillName
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterSkill


class DeleteCharacterSkill(CommitEntrypoint):
    """人物のスキルを消す。来歴の行と、その行を知る相手の行も消える。"""

    def __init__(self, character_skill_id: int):
        self.character_skill_id = character_skill_id

    def execute(self, s: Session) -> CharacterSkillName:
        record = common_query.get_row(s, CharacterSkill, self.character_skill_id)
        deleted = CharacterSkillName.model_validate(record)
        s.delete(record)
        return deleted
