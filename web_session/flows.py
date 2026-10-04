#!/usr/bin/env python3
"""web のセッションの Claude が入口を呼ぶ口。

claude を叩く入口(`gui/api/interface.py` の `claude` が立つもの)は、手元と同じ入口を、db の段を呼ぶ口だけ
API に差し替えて(`data_access_logic.caller.calling`)このセッションで回す。流れは `data_access_logic/flows/` にある。
db だけの入口は、API の入口(`/api/interface/{id}`)をそのまま呼ぶ。
"""
from __future__ import annotations

from typing import Any

from data_access_logic.caller import calling
from gui.api import interface
from web_session.api import call, run_entrance


def run(entrance_id: str, args: dict[str, Any]) -> Any:
    """引数を入口の型注釈のモデルに読み、結果を JSON にして返す。"""
    entrance = interface.entrance_of(entrance_id)
    if not entrance.claude:
        return run_entrance(entrance_id, args)
    with calling(call):
        return interface.call(entrance, interface.prepare(entrance, args))
