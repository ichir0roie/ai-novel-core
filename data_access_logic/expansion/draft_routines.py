#!/usr/bin/env python3
"""決まった居場所(`character_routine`)の無い人物に、AI が毎日通う所と時間を決めて足す(出自は ai)。

    DraftRoutines(character_ids=None, around_character_id=None, time=None).show()

人物モード(`SimulateDay`)で動かしていない人物は、決まった居場所の行が無いと、住まいにいて昼は留守(どこにもいない)になる。
`character_ids` は名指しした人物。`around_character_id` を渡すと、その人物のいるエリア(詳細の場所の一番近い、詳細でない上の場所)の
詳細の場所に住む人物も足す(`around_character_id` の人物は、`character_ids` に名指ししなければ足さない)。そのうち決まった居場所の行が今あるもの・詳細の場所に住んでいないものは外し、わけを返す
(`constants.ROUTINE_DRAFT_LIMIT` 人まで)。人物像・行動原理・来歴・関係とエリアの行ける場所から、毎日通う所を時間帯(朝・昼・夜)ごとに、人物ごとに一度 AI に決めさせ、
暦の時に割り直して足す(続く時間帯で同じ場所・同じことなら一行にまとめる)。
`time` はいつの人物で決めるか。省けば、名指しした最初の人物(無ければ `around_character_id`)が最後に出た時刻。足した行は期間を持たない。
"""
from __future__ import annotations

from data_access_logic.entrypoint import Entrypoint
from data_access_logic.expansion.routines import RoutineForm, RoutineRun
from data_access_logic.flows import routine
from db.stamp import Stamp


class DraftRoutines(Entrypoint):
    def __init__(self, character_ids: list[int] | None = None, around_character_id: int | None = None,
                 time: Stamp | str | None = None):
        self.character_ids = character_ids
        self.around_character_id = around_character_id
        self.time = time

    def result(self) -> RoutineRun:
        return routine.draft_routines(RoutineForm(character_ids=self.character_ids or [],
                                                  around_character_id=self.around_character_id,
                                                  time=Stamp.parse(self.time)))

    def run(self) -> dict:
        return self.result().model_dump(mode="json")
