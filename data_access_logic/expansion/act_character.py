#!/usr/bin/env python3
"""人物モード。人物が自分から一手を打ち、その結果を世界に足す(`.docs/world-expansion.md` の「人物モード」)。

    ActCharacter(character_id=None, time=None, nudge=None, seed=None, act_count=1, story_id=None,
                 parent_event_id=None, partner_ids=None).show()

一回の実行で `act_count` 手(`constants.ACT_RUN_LIMIT` まで)を、手ごとに順に組み、最後にまとめて一度だけ裁く。
`character_id` は一手目の人物。省けば(二手目からも)、本文のある最新の話(一手目を名指ししたら、その人物が登場した最新の話)の
登場人物から、行動力の重みで引く(主要人物も含める)。`time` だけを渡したときは、その時刻に生きて居場所があり、気力と手数の残る
サブキャラクターから引く。同じ実行で同じ人物は二度動かない。
`time` を省けば、その人物が最後に出た時刻(本文のある話のうち登場した最新の話と、それより後に AI が足した出来事。作者の先の筋は数えない。
作品の世界の今から取り残された人物は世界の今)から `constants.ACT_INTERVAL_DAYS` の範囲で日を空け、一日のうち起きている時間帯に置いて、
気力と手数が戻るまで待たせた時刻。
`time` を渡して、その時刻に気力か手数が足りなければ、その手は失敗として返す。
人物はその時刻に知ることのできるデータ(`ReadKnowledge` と同じ)と、目の前にいる人物・場所の近ごろの出来事・追っている企てだけから
一手(内心・狙い・行動・言葉)を決める。目の前にいる相手(名を知らない相手も)を巻きこみたければ、相手にも同じ材料で手番を返させ、交互に言葉を交わす。
裁く段は、実行の手をまとめて、サイコロの成り行きと影響の枠(動いた人物の影響力で決まる幅)に沿って出来事として記録する。
枠をはみ出た分と、動いた人物より影響力が上の人物の人となりの変化・住まいの移動は切る。
足すのは、出来事(大きな企ては親の出来事にし、一手ごとの出来事をその子にする)、当事者の来歴、事柄(アイデアと呼び名。知った人物を知る相手に)、
現れた人物・対象と、動いた人物との関係、居場所の移動(今の行に end を入れ、移動先の行を足す)。既にある行は消さず、end のほかは直さない。
一手ごとに展開(mode=character)を一つ立てて記録するので、`RevertExpansion` で一手ずつ取り消せる。`nudge` は作者からの軽い方向づけ。
`story_id` は `time` を読む暦の作品(人物を渡さずに `time` を渡すとき)。一手ごとの時刻は、引いた人物の暦で数える。
`parent_event_id` は作者が置いた親の出来事で、渡すと一手目の人物(`character_id` 必須)を親の期間の中で動かし、`time` を省けば
人物が最後に出た時刻から日を空けた時刻を親の始まりより後に寄せる。語り部が親とその先祖の本文、親の子のうち一手の前後に置かれた
出来事をもとに場を整え、裁く段はそれに逆らわない記録にし、一手の出来事を企てでなく親の子にする。`partner_ids` は一手目の人物の
目の前に居合わせさせる人物で、住まいを問わず居合わせる人物の頭に入り、巻きこめる相手になる。
"""
from __future__ import annotations

from data_access_logic.entrypoint import Entrypoint
from data_access_logic.expansion.act_models import ActRun
from data_access_logic.flows import act
from db.stamp import Stamp


class ActCharacter(Entrypoint):
    def __init__(self, character_id: int | None = None, time: Stamp | str | None = None, nudge: str | None = None,
                 seed: int | None = None, act_count: int = 1, story_id: int | None = None,
                 parent_event_id: int | None = None, partner_ids: list[int] | None = None):
        # 引数の時刻を読む暦を決めるだけ(`gui/api/interface.call` が引数から作品を立てる)
        self.story_id = story_id
        self.character_id = character_id
        self.time = time
        self.nudge = nudge
        self.seed = seed
        self.act_count = act_count
        self.parent_event_id = parent_event_id
        self.partner_ids = partner_ids

    def result(self) -> ActRun:
        return act.act_character(self.character_id, self.time, self.nudge, self.seed, self.act_count,
                                 parent_event_id=self.parent_event_id, partner_ids=self.partner_ids)

    def run(self) -> dict:
        # 手ごとに引いた人物の暦が違いうるので、手の時刻はその手の暦で書き出す
        return self.result().dumped()
