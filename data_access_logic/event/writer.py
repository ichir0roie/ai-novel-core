#!/usr/bin/env python3
"""本文(`text`)の空いた出来事に、名前・場所・当事者から記録の本文だけを書く。書けなければ空のまま残す。

db だけの段(`text_targets` → 要約を揃える → `text_material` → `save_event_text`)と、AI だけの段(`text_draft`)に分けてある。
流れ(`data_access_logic/flows/event.py`)がつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions.materials import EVENT_PARTICIPANT_NOTE, LATER_EVENTS_NOTE, TIME_NOTE
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import participants_at
from data_access_logic.event.summary import events_of
from data_access_logic.event.writer_models import (
    EventTextDraft, EventTextMaterial, EventTextMaterialSerialized, TextlessEvent,
)
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Character, Event, EventCharacter, StyleScope

logger = logging.getLogger(__name__)

# 出来事の記録の本文(event_text)の形。記録を起こす段(`progress.py`)も使う
EVENT_TEXT_FORMAT = """\
出来事の本文は、物語でなく、誰が何をして何を言ったかの記録にする。
- 起きた順に、一行に一件、人物・対象それぞれを主語にして書く。行動は誰が誰に何を使って何をしたか、言動は誰が誰に何を言ったか(求めた・断った・約束した・明かした・責めたなど)の要旨。
- 数・期間・物の名前・場所の名前・人物の名前と、実際に取った行動(求めた物・動かした量・出した命令・移った先)を書く。
- きっかけには、渡された場所の説明・環境・人間関係・地名のうち一つ以上を名指しで使う。
- 最後の一〜二行に、前と後で何が変わったか(立場・所属・取り決め・資源の量・力関係・居場所など)を書く。
- 全体で10行ほど。"""

_SYSTEM = f"""\
ある出来事の名前・時刻・場所・当事者などを渡すので、名前に沿った出来事として、記録の本文を書く。

{EVENT_TEXT_FORMAT}

{EVENT_PARTICIPANT_NOTE}

{LATER_EVENTS_NOTE}

{TIME_NOTE}"""


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
        "この出来事の記録の本文を書く。",
    ])
    return ai.generate(prompt, EventTextDraft, system=_SYSTEM, style_scope=StyleScope.EVENT)


def save_event_text(s: Session, event_id: int, draft: EventTextDraft | None) -> Event:
    record = s.get_one(Event, event_id)
    if draft is None:
        logger.warning(f"{record.name}(id={record.id}): 本文を書けなかったので空のまま残す")
    else:
        record.text = draft.text
        s.flush()
        logger.info(f"{record.name}(id={record.id}): 本文を書いた({len(record.text)}字)")
    return record
