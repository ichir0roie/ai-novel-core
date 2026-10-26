#!/usr/bin/env python3
"""既にある来歴・呼び名の行に、知る相手を一人(か一つの場所)足す。今ある知る相手には触れない。
人物が話を聞いて知った、噂が町に広まった、などを足すのに使う。`table` は来歴・呼び名の表の名前。

    AddKnower(table="character_history", row_id=40, knower=KnowerRow(knower_id=7, start="1200/05/01")).show()
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.appending import AppendedRow, appended, check_knowers
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.knowers import KnowerRow
from data_access_logic.query import common_query
from db.child_lists import child_model
from db.schema import CharacterHistory, CharacterSkillHistory, IdeaHistory, LocationHistory

_HISTORIES = {model.__tablename__: model for model in (CharacterHistory, CharacterSkillHistory, IdeaHistory, LocationHistory)}

KnownTable = Literal["character_history", "character_skill_history", "idea_history", "location_history"]


class AddKnower(CommitEntrypoint):
    def __init__(self, table: KnownTable, row_id: int, knower: KnowerRow):
        self.table = table
        self.row_id = row_id
        self.knower = knower

    def execute(self, s: Session) -> AppendedRow:
        history_model = _HISTORIES[self.table]
        history = common_query.get_row(s, history_model, self.row_id)
        check_knowers(s, [self.knower])
        knower_model = child_model(history_model, "knowers")
        foreign_key = next(column.key for column in knower_model.__table__.columns
                           if any(key.column.table.name == self.table for key in column.foreign_keys))
        same = (knower_model.knower_id == self.knower.knower_id if self.knower.knower_id is not None
                else knower_model.location_id == self.knower.location_id)
        if s.scalar(select(knower_model.id).where(getattr(knower_model, foreign_key) == history.id, same)) is not None:
            raise ValueError(f"{self.table} id={history.id} の知る相手に、もう入っている")
        row = knower_model(**{foreign_key: history.id})
        self.knower.write_to(row)
        s.add(row)
        return appended(s, row)
