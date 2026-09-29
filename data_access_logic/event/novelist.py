#!/usr/bin/env python3
"""記録として起こした出来事の本文(`text`)を、話と同じ小説の形に書き直す。書けなければ記録のまま残す。"""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import event_writing
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.instructions.style import EVENT_NOVEL_TARGET_LETTERS
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import event_characters_at
from data_access_logic.character.models import CharacterBase
from data_access_logic.event.novelist_models import EventNovelDraft, EventNovelMaterialSerialized, RecordedEvent
from data_access_logic.event.summary import summarized_events
from data_access_logic.idea.context import gather_ideas
from data_access_logic.idea.links import link
from data_access_logic.query import common_query
from db.schema import Event, EventCharacter


def _system_prompt(shared_style_extra: str, style_extra: str) -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
ある出来事の記録と、場所・当事者・当事者それぞれの直前の出来事などを日本語の見出しを付けた JSON で渡すので、この出来事を小説の本文に書き起こしてください。
場面の指定は、ジャンルや場面を一言で決めたものです。渡したときは、その味わいが伝わるように書いてください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{IDEA_CONTEXT_INSTRUCTION}
{event_writing.event_novel_instruction(shared_style_extra=shared_style_extra, style_extra=style_extra)}"""


def _novel_material(
    s: Session, ai: AIClient, event_id: int, focus_character_id: int | None, scene: str | None,
) -> EventNovelMaterialSerialized:
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
    # 要約・候補のアイデアの commit で読み込んだ関連が期限切れになるので、AI を呼ぶ前にマテリアルへ写しておく
    main_event = RecordedEvent.model_validate(event)
    characters = [link.character for link in event.event_characters]
    focus = next((character for character in characters if character.id == focus_character_id), None)
    focus_character = CharacterBase.model_validate(focus) if focus is not None else None
    time = main_event.start or main_event.time
    place_id = event.location_id

    return EventNovelMaterialSerialized(
        main_event=main_event,
        focus_character=focus_character,
        scene=scene,
        event_characters=event_characters_at(s, ai, characters, time),
        later_events=summarized_events(
            s, ai,
            common_query.events_after_select(
                place_id, [character.id for character in characters], time, limit=constants.LATER_EVENT_LIMIT)),
        ideas=gather_ideas(s, f"{main_event.name}\n{main_event.text}", ai, place_id, main_event.time),
    )


def novelize_event(
    s: Session,
    ai: AIClient,
    event_id: int,
    focus_character_id: int | None = None,
    scene: str | None = None,
    shared_style_extra: str = "",
    style_extra: str = "",
) -> Event:
    material = _novel_material(s, ai, event_id, focus_character_id, scene)

    letters = f"{EVENT_NOVEL_TARGET_LETTERS[0]}〜{EVENT_NOVEL_TARGET_LETTERS[1]}字"
    if material.focus_character is not None:
        viewpoint = f"{material.focus_character.name}を"
    elif scene:
        viewpoint = "当事者のうち場面の指定が一番よく伝わる一人を"
    else:
        viewpoint = "当事者のうちこの出来事の中心にいる一人を"
    prompt = "\n".join([
        material.model_dump_json(indent=2),
        f"この出来事を、{viewpoint}視点人物にした{letters}の小説の本文に書き起こしてください。",
    ])
    decided = ai.try_generate_json(
        prompt, EventNovelDraft.model_json_schema(), system=_system_prompt(shared_style_extra, style_extra),
        timeout=constants.EVENT_NOVEL_TIMEOUT)

    record = s.get_one(Event, event_id)
    try:
        record.text = EventNovelDraft.model_validate(decided).text
        print(f"[data_access_logic/event] {record.name}(id={record.id}): 本文を小説にした({len(record.text)}字)")
    except ValidationError as error:
        print(f"[data_access_logic/event] {record.name}(id={record.id}): 本文を小説にできなかったので記録のまま残す: {error}")
    link(s, record, material.ideas.linked)
    s.commit()
    return record
