#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from data_access_logic.character.form import KnowledgeChange, KnowledgeForm
from data_access_logic.character.read_known_rows import known_rows
from data_access_logic.character.record import KnownRows
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import Character, CharacterHistory, CharacterHistoryKnower, IdeaHistory, IdeaHistoryKnower, KnowerMixin


def _apply[K: KnowerMixin](knowers: list[K], knower_id: int, change: KnowledgeChange, knower: Callable[[], K]) -> None:
    row = next((row for row in knowers if row.knower_id == knower_id), None)
    if not change.known:
        if row is not None:
            knowers.remove(row)
        return
    if row is None:
        row = knower()
        row.knower_id = knower_id
        knowers.append(row)
    row.start = change.start


class UpdateKnowledge(CommitEntrypoint):
    """人物を、人物の来歴・アイデアの履歴の行の知る相手に、まとめて入れる・外す(GUI の知識整理)。
    場所として入っている知る相手の行には触らない。直したあとの、その人物が知る行を返す。"""

    def __init__(self, knowledge: KnowledgeForm):
        self.knowledge = knowledge

    def execute(self, s: Session) -> KnownRows:
        form = self.knowledge
        common_query.get_row(s, Character, form.knower_id)
        # 知られる行は変数に持ってから knowers を直す(セッションはまだ直していない行を弱く持つので、knowers だけを取ると行が消えて直せない)
        for change in form.character_histories:
            character_history = common_query.get_row(s, CharacterHistory, change.id)
            _apply(character_history.knowers, form.knower_id, change, CharacterHistoryKnower)
        for change in form.idea_histories:
            idea_history = common_query.get_row(s, IdeaHistory, change.id)
            _apply(idea_history.knowers, form.knower_id, change, IdeaHistoryKnower)
        s.flush()
        return known_rows(s, form.knower_id)
