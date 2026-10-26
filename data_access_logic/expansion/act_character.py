#!/usr/bin/env python3
"""人物モード。人物が自分から一手を打ち、その結果を世界に足す(`.docs/world-expansion.md` の「人物モード」)。

    ActCharacter(character_id=None, time=None, nudge=None, seed=None).show()

`character_id` を省けば、世界の最新の時刻に生きて居場所のある人物のサブキャラクターから、行動力の重みで引く。
`time` を省けば、その人物が最後に出た出来事・話から `constants.ACT_INTERVAL_DAYS` の範囲で日を空けた時刻(出たことが無ければ世界の最新の時刻)。
人物はその時刻に知ることのできるデータ(`ReadKnowledge` と同じ)と、目の前にいる人物・場所の近ごろの出来事・追っている企てだけから
一手(内心・狙い・行動・言葉)を決め、作者の目で、サイコロの成り行きに沿ってその結果を出来事として記録する。
足すのは、出来事(大きな企ては親の出来事にし、一手ごとの出来事をその子にする)、当事者の来歴、事柄(アイデアと呼び名。知った人物を知る相手に)、
現れた人物・対象と、動いた人物との関係、居場所の移動(今の行に end を入れ、移動先の行を足す)。既にある行は消さず、end のほかは直さない。
一手ごとに展開(mode=character)を一つ立てて記録するので、`RevertExpansion` で取り消せる。`nudge` は作者からの軽い方向づけ。
"""
from __future__ import annotations

from data_access_logic.entrypoint import Entrypoint
from data_access_logic.expansion.act_models import ActedCharacter
from data_access_logic.flows import act
from db.stamp import Stamp


class ActCharacter(Entrypoint):
    def __init__(self, character_id: int | None = None, time: Stamp | str | None = None, nudge: str | None = None,
                 seed: int | None = None):
        self.character_id = character_id
        self.time = time
        self.nudge = nudge
        self.seed = seed

    def result(self) -> ActedCharacter:
        return act.act_character(self.character_id, self.time, self.nudge, self.seed)
