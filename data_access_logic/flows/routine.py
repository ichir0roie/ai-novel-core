#!/usr/bin/env python3
"""決まった居場所(`character_routine`)の無い人物に、AI が毎日通う所と時間を決めて足す流れ(`expansion/routines.py`)。

人物ごとに一度 AI を呼び、得たその場で足す(後の人物で AI が落ちても、それまでの行は残す)。足した行の出自は ai。
"""
from __future__ import annotations

import json
import logging

from ai.claude_code import ai_client
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.caller import call
from data_access_logic.expansion import routines
from data_access_logic.expansion import steps as expansion_steps
from data_access_logic.expansion.routines import (
    DraftedRoutines, RoutineAddForm, RoutineDraft, RoutineForm, RoutineRun, RoutineSkipped,
)
from db.schema import StyleScope
from db.writer import generated

logger = logging.getLogger(__name__)

_SYSTEM = """\
物語の人物一人の、毎日決まって過ごす時間帯と場所(仕事・持ち場・日課)を決める。その人物が物語に出ていない日に、どこにいるかに使う。
人物像・行動原理・来歴・関係から、その人物の暮らしで毎日のように通う所だけを、行ける場所の中から選ぶ。勤め先・店・持ち場の名前が関係や来歴にあれば、それに当たる場所にする。
住まいにいる時間は書かない(決まった居場所に当たらない時間は住まいにいる)。決まって通う所が無い人物(家で過ごす・幼い・旅の途中・行ける場所に当たる所が無い)は空にする。
時間は「時間帯」(朝・昼・夜)のどれかで選び、時間帯ごとに一つまでにする。同じ場所で同じことを続けるなら、時間帯ごとに同じ場所・同じしていることを書く。"""


def draft_routines(form: RoutineForm, ai: AIClient = ai_client) -> RoutineRun:
    targets = call(expansion_steps.routine_targets, form)
    run = RoutineRun(time=targets.time, skipped=targets.skipped)
    for character in targets.characters:
        prompt = "\n".join([json.dumps(character.for_prompt(), ensure_ascii=False, indent=2),
                            f"{character.name}の、毎日決まって過ごす時間帯と場所を決める。"])
        draft = ai.generate(prompt, RoutineDraft, system=_SYSTEM, style_scope=StyleScope.CHARACTER,
                            model=constants.ACT_MODEL, effort=constants.ACT_EFFORT)
        if draft is None:
            logger.warning(f"{character.name}(id={character.character_id})の決まった居場所が得られなかった")
            run.skipped.append(RoutineSkipped(character_id=character.character_id, name=character.name,
                                              reason="AI が答えなかった"))
            continue
        rows = routines.usable_rows(draft, character)
        if not rows:
            run.none.append(RoutineSkipped(character_id=character.character_id, name=character.name,
                                           reason="決まって通う所が無い"))
            continue
        with generated():
            added = call(expansion_steps.add_routines, RoutineAddForm(character_id=character.character_id, rows=rows))
        run.drafted.append(DraftedRoutines(character_id=character.character_id, name=character.name, routines=added))
    return run
