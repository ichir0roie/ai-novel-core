#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy.orm import selectinload

from ai.claude_code import ai_client
from ai.claude_code.interface._base import SessionEntrypoint, UnknownRecordError, reloaded
from ai.time_keeper import place_event_generator
from data_access_logic.event.form import EventForm
from data_access_logic.event.record import EventRecord
from db.schema import Event


class GenerateEvent(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、出来事を一件 AI に組み立てさせて足す。

    場所の出来事(`place_event`)と同じ生成(候補を挙げてサイコロで選び、記録して小説の本文にする)を、
    下書きの名前・記録を場面の指定に、時刻・場所・当事者を決まった値として回す。
    時刻を省けば世界の最新の出来事の時刻、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。

    `id` を渡せば、その出来事の本文(text)が空のときに限り、記録・当事者・関連する設定から AI に
    小説の本文だけを書かせて埋める(名前・時刻・場所・当事者は変えない)。
    """

    def __init__(self, event: EventForm | None = None, seed: int | None = None,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.event = event or EventForm()
        self.seed = seed
        self.shared_style_extra = shared_style_extra
        self.style_extra = style_extra
        self.ai = ai

    def execute(self, session) -> EventRecord:
        if self.event.id is not None:
            record = session.get(Event, self.event.id)
            if record is None:
                raise UnknownRecordError(f"id={self.event.id} という出来事が見つからない")
            place_event_generator.complete_text(
                session, self.ai, record,
                shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        else:
            record = place_event_generator.generate_from_draft(
                session, self.ai, self.event, random.Random(self.seed),
                shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        return EventRecord.model_validate(reloaded(session, record, selectinload(Event.event_characters)))
