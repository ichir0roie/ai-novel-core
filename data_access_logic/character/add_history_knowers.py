#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.record import AddedHistoryKnowers
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterHistory, CharacterHistoryKnower, IdeaHistory, IdeaHistoryKnower
from db.stamp import Stamp


class AddHistoryKnowers(CommitEntrypoint):
    """人物を、選んだ人物の来歴・アイデアの履歴の行の知る相手に足す(GUI の知識整理)。すでに知る相手に入っている行はそのままにする。"""

    def __init__(self, knower_id: int, character_history_ids: list[int] | None = None,
                 idea_history_ids: list[int] | None = None, start: Stamp | str | None = None):
        self.knower_id = knower_id
        self.character_history_ids = character_history_ids or []
        self.idea_history_ids = idea_history_ids or []
        self.start = start

    def execute(self, s: Session) -> AddedHistoryKnowers:
        common_query.get_row(s, Character, self.knower_id)
        start = Stamp.parse(self.start)
        added = AddedHistoryKnowers(character_history_ids=[], idea_history_ids=[])
        for history_id in dict.fromkeys(self.character_history_ids):
            character_history = common_query.get_row(s, CharacterHistory, history_id)
            if all(knower.knower_id != self.knower_id for knower in character_history.knowers):
                character_history.knowers.append(CharacterHistoryKnower(knower_id=self.knower_id, start=start))
                added.character_history_ids.append(history_id)
        for history_id in dict.fromkeys(self.idea_history_ids):
            idea_history = common_query.get_row(s, IdeaHistory, history_id)
            if all(knower.knower_id != self.knower_id for knower in idea_history.knowers):
                idea_history.knowers.append(IdeaHistoryKnower(knower_id=self.knower_id, start=start))
                added.idea_history_ids.append(history_id)
        return added
