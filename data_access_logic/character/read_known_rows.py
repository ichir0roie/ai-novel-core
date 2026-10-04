#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.character.record import KnownCharacterHistory, KnownIdeaHistory, KnownRows
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterHistory, CharacterHistoryKnower, CharacterKnower, IdeaHistory, IdeaHistoryKnower


def known_rows(s: Session, knower_id: int) -> KnownRows:
    return KnownRows(
        character_ids=list(s.scalars(select(CharacterKnower.character_id).where(CharacterKnower.knower_id == knower_id)
                                     .order_by(CharacterKnower.character_id))),
        character_histories=[KnownCharacterHistory.model_validate(row) for row in s.scalars(
            select(CharacterHistory).join(CharacterHistoryKnower).where(CharacterHistoryKnower.knower_id == knower_id)
            .order_by(CharacterHistory.id))],
        idea_histories=[KnownIdeaHistory.model_validate(row) for row in s.scalars(
            select(IdeaHistory).join(IdeaHistoryKnower).where(IdeaHistoryKnower.knower_id == knower_id)
            .order_by(IdeaHistory.id))],
    )


class ReadKnownRows(SessionEntrypoint):
    """人物が知る相手に人物として入っている、人物の芯・人物の来歴・アイデアの履歴の行を読む(GUI の知識整理の木の印)。"""

    def __init__(self, knower_id: int):
        self.knower_id = knower_id

    def execute(self, s: Session) -> KnownRows:
        common_query.get_row(s, Character, self.knower_id)
        return known_rows(s, self.knower_id)
