#!/usr/bin/env python3
"""本文(`text`)の空いた出来事に、名前・場所・当事者から記録の本文だけを書く。書けなければ空のまま残す。

db だけの段(`text_targets` → 要約を揃える → `text_material` → `save_event_text`)と、AI だけの段(`text_draft`)に分けてある。
手元では `write_event_text` がつなぎ、web のセッションでは `web_session/event.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION, EVENT_RECORD_INSTRUCTION, EVENT_SITUATION_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import participants_at
from data_access_logic.event.summary import events_of
from data_access_logic.event.writer_models import (
    EventTextDraft, EventTextMaterial, EventTextMaterialSerialized, TextlessEvent,
)
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets, refresh
from db.schema import Character, Event, EventCharacter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある場所に起きたことを記録する設定作家です。
ある出来事の名前・時刻・場所・当事者などを日本語の見出しを付けた JSON で渡すので、この出来事の記録の本文を書いてください。
出来事の名前は、ジャンルや場面を一言で決めたものです。その中身に沿った出来事にしてください。
{EVENT_SITUATION_INSTRUCTION}
{EVENT_AGE_INSTRUCTION}
{EVENT_RECORD_INSTRUCTION}"""


def _event(s: Session, event_id: int) -> Event:
    event = s.scalar(
        select(Event)
        .where(Event.id == event_id)
        .options(
            joinedload(Event.location),
            selectinload(Event.event_characters).joinedload(EventCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise ValueError(f"出来事 id={event_id} が見つからない")
    return event


def _characters(event: Event) -> list[Character]:
    return [link.character for link in event.event_characters]


def _later_events_select(event: Event) -> Select[Event]:
    return common_query.events_after_select(
        event.location_id, [character.id for character in _characters(event)], event.start or event.time,
        limit=constants.LATER_EVENT_LIMIT)


def text_targets(s: Session, event_id: int) -> SummaryTargets:
    event = _event(s, event_id)
    return SummaryTargets(event_ids=[later.id for later in s.scalars(_later_events_select(event)).all()])


def text_material(s: Session, event_id: int) -> EventTextMaterialSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    event = _event(s, event_id)
    return EventTextMaterialSerialized(
        event=TextlessEvent.model_validate(event),
        participants=participants_at(s, _characters(event), event.start or event.time),
        later_events=events_of(s, _later_events_select(event)),
    )


def text_draft(ai: AIClient, material: EventTextMaterial) -> EventTextDraft | None:
    prompt = "\n".join([
        EventTextMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "この出来事の記録の本文を書いてください。",
    ])
    return ai.generate(prompt, EventTextDraft, system=_SYSTEM_PROMPT)


def save_event_text(s: Session, event_id: int, draft: EventTextDraft | None) -> Event:
    record = s.get_one(Event, event_id)
    if draft is None:
        logger.warning(f"{record.name}(id={record.id}): 本文を書けなかったので空のまま残す")
    else:
        record.text = draft.text
        s.flush()
        logger.info(f"{record.name}(id={record.id}): 本文を書いた({len(record.text)}字)")
    return record


def write_event_text(s: Session, ai: AIClient, event_id: int) -> Event:
    refresh(s, ai, text_targets(s, event_id))
    record = save_event_text(s, event_id, text_draft(ai, text_material(s, event_id)))
    s.commit()
    return record
