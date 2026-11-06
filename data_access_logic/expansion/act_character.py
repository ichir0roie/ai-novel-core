#!/usr/bin/env python3
"""人物モード。人物が自分から一手を打ち、その結果を世界に足す(`.docs/world-expansion.md` の「人物モード」)。

    ActCharacter(character_id=None, time=None, nudge=None, seed=None, act_count=1).show()

一回の実行で `act_count` 手(`constants.ACT_RUN_LIMIT` まで)を、手ごとに順に組み、最後にまとめて一度だけ裁く。
`character_id` は一手目の人物で、省けば(二手目からも)世界の最新の時刻に生きて居場所があり、気力と手数の残るサブキャラクターから、
行動力の重みで引く。同じ実行で同じ人物は二度動かない。
`time` を省けば、その人物が最後に出た出来事・話から `constants.ACT_INTERVAL_DAYS` の範囲で日を空け、気力と手数が戻るまで待たせた時刻。
`time` を渡して、その時刻に気力か手数が足りなければ、その手は失敗として返す。
人物はその時刻に知ることのできるデータ(`ReadKnowledge` と同じ)と、目の前にいる人物・場所の近ごろの出来事・追っている企てだけから
一手(内心・狙い・行動・言葉)を決める。目の前にいて名前を知っている相手を巻きこみたければ、相手にも同じ材料で手番を返させ、交互に言葉を交わす。
裁く段は、実行の手をまとめて、サイコロの成り行きと影響の枠(動いた人物の影響力で決まる幅)に沿って出来事として記録する。
枠をはみ出た分と、動いた人物より影響力が上の人物の人となりの変化・住まいの移動は切る。
足すのは、出来事(大きな企ては親の出来事にし、一手ごとの出来事をその子にする)、当事者の来歴、事柄(アイデアと呼び名。知った人物を知る相手に)、
現れた人物・対象と、動いた人物との関係、居場所の移動(今の行に end を入れ、移動先の行を足す)。既にある行は消さず、end のほかは直さない。
一手ごとに展開(mode=character)を一つ立てて記録するので、`RevertExpansion` で一手ずつ取り消せる。`nudge` は作者からの軽い方向づけ。
"""
from __future__ import annotations

from data_access_logic.entrypoint import Entrypoint
from data_access_logic.expansion.act_models import ActRun
from data_access_logic.flows import act
from db.stamp import Stamp


class ActCharacter(Entrypoint):
    def __init__(self, character_id: int | None = None, time: Stamp | str | None = None, nudge: str | None = None,
                 seed: int | None = None, act_count: int = 1):
        self.character_id = character_id
        self.time = time
        self.nudge = nudge
        self.seed = seed
        self.act_count = act_count

    def result(self) -> ActRun:
        return act.act_character(self.character_id, self.time, self.nudge, self.seed, self.act_count)
