#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import (
    CharacterHistoryEntry, CharacterSkillEntry, CharacterSkillHistoryEntry, CharacterTextEntry, IdeaHistoryEntry,
    KnowableRows,
)
from data_access_logic.character.skills import skills_of
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterHistory, CharacterSkillHistory, Idea


def _dated_order(row: CharacterHistory | CharacterSkillHistory) -> tuple[bool, int, int]:
    """年の決まっていない行は最後。"""
    return row.start is None, row.start or 0, row.id


class ReadKnowableRows(SessionEntrypoint):
    """人物の芯と来歴とスキルの来歴か、アイデアの履歴の行を、id と知る相手つきで読む。GUI の知識整理で、行を選んで知る相手を付け外しするのに使う。"""

    def __init__(self, character_id: int | None = None, idea_id: int | None = None):
        if (character_id is None) == (idea_id is None):
            raise ValueError("character_id か idea_id のどちらか一方を渡す")
        self.character_id = character_id
        self.idea_id = idea_id

    def execute(self, s: Session) -> KnowableRows:
        if self.character_id is not None:
            character = common_query.get_row(s, Character, self.character_id)
            rows = sorted(character.histories, key=_dated_order)
            return KnowableRows(character=CharacterTextEntry.model_validate(character),
                                character_histories=[CharacterHistoryEntry.model_validate(row) for row in rows],
                                character_skills=[
                                    CharacterSkillEntry(id=skill.id, name=skill.name, histories=[
                                        CharacterSkillHistoryEntry.model_validate(row)
                                        for row in sorted(skill.histories, key=_dated_order)])
                                    for skill in skills_of(s, character.id)],
                                idea_histories=[])
        assert self.idea_id is not None
        idea = common_query.get_row(s, Idea, self.idea_id)
        rows = sorted(idea.histories, key=lambda row: (row.start is not None, row.start or 0, row.id))
        return KnowableRows(character_histories=[], character_skills=[],
                            idea_histories=[IdeaHistoryEntry.model_validate(row) for row in rows])
