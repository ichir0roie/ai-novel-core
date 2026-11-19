#!/usr/bin/env python3
"""入口の引数から決まる作品と、その作品の暦。web のセッション(`web_session/flows.py`)は db に繋がないので、流れを回す前に
これで作品と暦を受け取り、流れの中の時刻をその暦で読み書きする。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.story.record import ScopeRecord
from db import story_scope


class ReadScope(SessionEntrypoint):
    def __init__(self, args: dict[str, Any]):
        # 作品は、呼ぶ口(`gui/api/interface.call`)がこの引数から決めて立てている
        self.args = args

    def execute(self, s: Session) -> ScopeRecord:
        found = story_scope.current()
        if found is None:
            return ScopeRecord()
        return ScopeRecord(story_id=found.story_id, calendar=None if found.calendar is None else found.calendar.to_json())
