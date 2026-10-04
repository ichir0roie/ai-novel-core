#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.event.form import EventForm
from data_access_logic.event.record import GeneratedEvent
from data_access_logic.flows import event


class GenerateEvent(Entrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、出来事を一件 AI に組み立てさせて足す。

    候補を挙げてサイコロで選び、行動・言動を整理した記録にする生成を、
    下書きの名前・記録を場面の指定に、時刻・場所・当事者を決まった値として回す。
    時刻を省けば世界の最新の出来事の時刻、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。

    `id` を渡せば、その出来事の本文(text)が空のときに限り、名前・場所・当事者から AI に
    記録の本文だけを書かせて埋める(名前・時刻・場所・当事者は変えない)。
    """

    def __init__(self, event: EventForm | None = None, seed: int | None = None, ai: AIClient = ai_client):
        self.event = event
        self.seed = seed
        self.ai = ai

    def result(self) -> GeneratedEvent:
        return event.generate_event(self.event, self.seed, self.ai)
