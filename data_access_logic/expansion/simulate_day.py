#!/usr/bin/env python3
"""人物モード。渡した人物たちの一日を、0 時から暦の一時間ずつ動かし、その日の行動を世界に足す(`.docs/world-expansion.md` の「人物モード」)。

    SimulateDay(character_ids=None, date=None, nudge=None, seed=None, parent_event_id=None, story_id=None).show()

`character_ids` は動かす人物(`constants.DAY_CHARACTER_LIMIT` 人まで)。省けば、本文のある最新の話の登場人物(名前だけ出る人物を除く)。
`date` は動かす日(人物の暦の日付)。省けば、人物が最後に出た日(本文のある話と、それより後に AI が足した出来事)のうち一番遅い日の翌日。
動かせるのは、詳細の場所(`Location.map_detail`)にいる人物だけで、その日のあいだは、人物のいるエリア(詳細の場所の一番近い、詳細でない
上の場所)の詳細の場所のあいだを動く。詳細の場所にいない人物・その日をもう動かした人物・暦の違う人物は、失敗として返す。
一時間ごとに、人物ごとの手を並べて決める。作者の出来事・話の予定がある時間は予定で埋め、眠っている時間は眠気の規則で埋める。
同じ場所に居合わせた人物どうしは、相手がその一時間にしたことを受けて応じ、次の一時間の材料にも、目の前の人物がしたことが入る。
一時間ごとの行動は行動の表(`event_action`)に一行ずつ残し、一日の終わりに、人物ごとの一日を出来事一件にまとめて、当事者の来歴・
事柄(アイデアと呼び名)・現れた人物・住まいの移動・思いの増減を足す(足すことと `end` を付けることだけ)。
人物の一日ごとに展開(mode=character)を一つ立てて記録するので、`RevertExpansion` で人物の一日ごとに取り消せる。
`nudge` は作者からの軽い方向づけ。`parent_event_id` は作者が置いた親の出来事で、渡すと一日の出来事をその子にし、記録する段が親の筋に逆らわない
ように読む。`story_id` は `date` を読む暦の作品(人物を渡さないとき)。
"""
from __future__ import annotations

from data_access_logic.entrypoint import Entrypoint
from data_access_logic.expansion.act_models import DayRun
from data_access_logic.flows import act
from db.stamp import Stamp


class SimulateDay(Entrypoint):
    def __init__(self, character_ids: list[int] | None = None, date: Stamp | str | None = None, nudge: str | None = None,
                 seed: int | None = None, parent_event_id: int | None = None, story_id: int | None = None):
        # 引数の時刻を読む暦を決めるだけ(`gui/api/interface.call` が引数から作品を立てる)
        self.story_id = story_id
        self.character_ids = character_ids
        self.date = date
        self.nudge = nudge
        self.seed = seed
        self.parent_event_id = parent_event_id

    def result(self) -> DayRun:
        return act.simulate_day(self.character_ids, self.date, self.nudge, self.seed,
                                parent_event_id=self.parent_event_id)

    def run(self) -> dict:
        # その日の時刻は、動かした人物の暦で書き出す
        return self.result().dumped()
