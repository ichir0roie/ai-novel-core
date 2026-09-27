#!/usr/bin/env python3
from __future__ import annotations

import random

from ai.claude_code import ai_client
from sqlalchemy import select

from ai.claude_code.interface._base import SessionEntrypoint, UnknownRecordError
from ai.time_keeper import place_event_generator
from db.schema import Event, EventCharacter
from db.schema_pydantic import to_dict


class GenerateEvent(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、出来事を一件 AI に組み立てさせて足す。

    場所の出来事(`place_event`)と同じ生成(候補を挙げてサイコロで選び、記録して小説の本文にする)を、
    下書きの名前・記録を場面の指定に、時刻・場所・当事者を決まった値として回す。
    時刻を省けば世界の最新の出来事の時刻、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。

    `id` を渡せば、その出来事の本文(text)が空のときに限り、記録・当事者・関連する設定から AI に
    小説の本文だけを書かせて埋める(名前・時刻・場所・当事者は変えない)。
    """

    def __init__(self, event: dict | None = None, seed: int | None = None, *,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.event = dict(event or {})
        self.seed = seed
        self.shared_style_extra = shared_style_extra
        self.style_extra = style_extra
        self.ai = ai

    def execute(self, session) -> dict:
        draft = dict(self.event)
        event_id = draft.pop("id", None)
        if event_id is not None:
            return self._complete(session, event_id)
        record = place_event_generator.generate_from_draft(
            session, self.ai, draft, random.Random(self.seed),
            shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        session.refresh(record)
        # `Event.event_characters` は noload なので、中間テーブルを直接引く
        character_ids = list(session.scalars(select(EventCharacter.character_id)
                                             .where(EventCharacter.event_id == record.id).order_by(EventCharacter.id)))
        return {**to_dict(record), "character_ids": character_ids}

    def _complete(self, session, event_id: int) -> dict:
        record = session.get(Event, event_id)
        if record is None:
            raise UnknownRecordError(f"id={event_id} という出来事が見つからない")
        place_event_generator.complete_text(
            session, self.ai, record,
            shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        character_ids = list(session.scalars(select(EventCharacter.character_id)
                                             .where(EventCharacter.event_id == record.id).order_by(EventCharacter.id)))
        return {**to_dict(record), "character_ids": character_ids}
