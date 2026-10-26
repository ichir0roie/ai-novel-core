#!/usr/bin/env python3
"""人物の来歴の行を一つ足す。今ある行には触れない。知る相手を渡さなければ本人だけが知る。

    AppendCharacterHistory(character_id=5, history=CharacterHistoryRow(start="1200/04/01", description="港で疫病に罹る")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.appending import AppendedRow, appended, check_knowers
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.child_lists import appended_history
from db.schema import Character, CharacterHistory


class AppendCharacterHistory(CommitEntrypoint):
    def __init__(self, character_id: int, history: CharacterHistoryRow):
        self.character_id = character_id
        self.history = history

    def execute(self, s: Session) -> AppendedRow:
        character = common_query.get_row(s, Character, self.character_id)
        check_knowers(s, self.history.knowers)
        row = appended_history(self.history, CharacterHistory, owner=character)
        row.character_id = character.id
        s.add(row)
        return appended(s, row)
