#!/usr/bin/env python3
"""本文(`text`)の空いた出来事に、名前・場所・当事者から記録の本文だけを書く。書けなければ空のまま残す。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION, EVENT_RECORD_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import participants_at
from data_access_logic.event.summary import summarized_events
from data_access_logic.event.writer_models import EventTextDraft, EventTextMaterialSerialized, TextlessEvent
from data_access_logic.query import common_query
from db.schema import Event, EventCharacter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある場所に起きたことを記録する設定作家です。
ある出来事の名前・時刻・場所・当事者などを日本語の見出しを付けた JSON で渡すので、この出来事の記録の本文を書いてください。
出来事の名前は、ジャンルや場面を一言で決めたものです。その中身に沿った出来事にしてください。
当事者の性格の各軸は 無/低/並/高/必 の五段階です。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{EVENT_RECORD_INSTRUCTION}"""


def write_event_text(s: Session, ai: AIClient, event_id: int) -> Event:
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
    # 要約の commit で読み込んだ関連が期限切れになるので、要約を作る前にマテリアルへ写しておく
    textless = TextlessEvent.model_validate(event)
    characters = [link.character for link in event.event_characters]
    time = textless.start or textless.time
    participants = participants_at(s, characters, time)
    material = EventTextMaterialSerialized(
        event=textless,
        participants=participants,
        later_events=summarized_events(
            s, ai,
            common_query.events_after_select(
                event.location_id, [character.id for character in characters], time,
                limit=constants.LATER_EVENT_LIMIT)),
    )

    prompt = "\n".join([
        material.model_dump_json(indent=2),
        "この出来事の記録の本文を書いてください。",
    ])
    draft = ai.generate(prompt, EventTextDraft, system=_SYSTEM_PROMPT)

    record = s.get_one(Event, event_id)
    if draft is None:
        logger.warning(f"{record.name}(id={record.id}): 本文を書けなかったので空のまま残す")
    else:
        record.text = draft.text
        logger.info(f"{record.name}(id={record.id}): 本文を書いた({len(record.text)}字)")
    s.commit()
    return record
