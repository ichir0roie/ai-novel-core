#!/usr/bin/env python3
"""web のセッションの Claude が入口を呼ぶ口。

claude を叩く入口(`gui/api/interface.py` の `CLAUDE_ENTRANCES`)は、手元と同じ入口を、db の段を呼ぶ口だけ
API に差し替えて(`data_access_logic.caller.calling`)このセッションで回す。流れは `data_access_logic/flows/` にある。
db だけの入口は、API の入口(`/api/interface/{id}`)をそのまま呼ぶ。
"""
from __future__ import annotations

from typing import Any

from data_access_logic.caller import calling
from data_access_logic.entrance_args import built
from data_access_logic.story.record import ScopeRecord
from db import story_scope
from gui.api import interface
from web_session.api import call
from web_session.transport import run_entrance


def run(entrance_id: str, args: dict[str, Any]) -> Any:
    """引数を入口の型注釈のモデルに読み、結果を JSON にして返す。"""
    if entrance_id not in interface.CLAUDE_ENTRANCES:
        return run_entrance(entrance_id, args)
    # db に繋がないので、作品と暦は API に引数から決めてもらい、流れの中の時刻をその暦で読み書きする
    found = ScopeRecord.model_validate(run_entrance("story.read_scope.ReadScope", {"args": args}))
    with calling(call), story_scope.scoped(found.scope()):
        return built(interface.entrance_class(entrance_id), args).run()
