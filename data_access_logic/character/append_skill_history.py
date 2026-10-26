#!/usr/bin/env python3
"""スキルの来歴の行を一つ足す。今ある行には触れない。知る相手を渡さなければスキルを持つ本人だけが知る。

    AppendSkillHistory(character_skill_id=8, history=CharacterSkillHistoryRow(start="1200", description="薬の調合を覚える")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import AppendedRow, appended, check_knowers
from data_access_logic.character.record import CharacterSkillHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import appended_history
from db.schema import Character, CharacterSkill, CharacterSkillHistory


class AppendSkillHistory(CommitEntrypoint):
    def __init__(self, character_skill_id: int, history: CharacterSkillHistoryRow):
        self.character_skill_id = character_skill_id
        self.history = history

    def execute(self, s: Session) -> AppendedRow:
        skill = common_query.get_row(s, CharacterSkill, self.character_skill_id)
        check_knowers(s, self.history.knowers)
        row = appended_history(self.history, CharacterSkillHistory, owner=s.get_one(Character, skill.character_id))
        row.character_skill_id = skill.id
        s.add(row)
        return appended(s, row)
