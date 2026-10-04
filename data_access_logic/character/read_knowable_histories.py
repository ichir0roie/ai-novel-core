#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import CharacterHistoryEntry, IdeaHistoryEntry, KnowableHistories
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, Idea


class ReadKnowableHistories(SessionEntrypoint):
    """人物の来歴かアイデアの履歴の行を、id と知る相手つきで読む。GUI の知識整理で、行を選んで知る相手を足すのに使う。"""

    def __init__(self, character_id: int | None = None, idea_id: int | None = None):
        if (character_id is None) == (idea_id is None):
            raise ValueError("character_id か idea_id のどちらか一方を渡す")
        self.character_id = character_id
        self.idea_id = idea_id

    def execute(self, s: Session) -> KnowableHistories:
        if self.character_id is not None:
            character = common_query.get_row(s, Character, self.character_id)
            rows = sorted(character.histories, key=lambda row: (row.start is None, row.start or 0, row.id))
            return KnowableHistories(character_histories=[CharacterHistoryEntry.model_validate(row) for row in rows],
                                     idea_histories=[])
        assert self.idea_id is not None
        idea = common_query.get_row(s, Idea, self.idea_id)
        rows = sorted(idea.histories, key=lambda row: (row.start is not None, row.start or 0, row.id))
        return KnowableHistories(character_histories=[],
                                 idea_histories=[IdeaHistoryEntry.model_validate(row) for row in rows])
