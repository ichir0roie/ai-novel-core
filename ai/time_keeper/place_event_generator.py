#!/usr/bin/env python3
from __future__ import annotations

import json
import random

from sqlalchemy import select

from ai.instructions import event_writing
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.style import EVENT_NOVEL_TARGET_LETTERS, layout_novel_text
from ai.time_keeper import constants
from ai.time_keeper import event_progression_generator as progression
from ai.time_keeper import event_seed, idea_context
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from ai.time_keeper.character_event_generator import _latest_event, _previous_row, _sheet
from data_access_logic.query import world_createion_query
from data_access_logic.query.base import character_active_condition
from db.schema import Character, Event, EventCharacter, Location, Session, Stamp

def _novel_system_prompt(*, shared_style_extra: str = "", style_extra: str = "") -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
ある場所で起きた出来事の記録と、場所・当事者・当事者それぞれの直前の出来事・場面の指定を渡すので、この出来事を小説の本文に書き起こしてください。
場面の指定は、ジャンルや場面を一言で決めたものです。その味わいが伝わるように書いてください。
「関係する設定」を渡したときは、それを踏まえて書いてください。
「この時点より後に既に決まっている出来事」を渡したときは、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{event_writing.event_novel_instruction(shared_style_extra=shared_style_extra, style_extra=style_extra)}
JSON で答えてください。キーは text(本文)だけ。"""


# 文体の好み(舞台設定・既存の話から抽出した文体の癖など)を渡さない既定の文面。
_NOVEL_SYSTEM_PROMPT = _novel_system_prompt()

_NOVEL_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _members(session: Session, place_id: int, time: Stamp) -> list[Character]:
    """場所を名指しで頼まれるので、ランダム生成の対象か(active_random_generation)は見ない。"""
    busy_ids = set(session.scalars(world_createion_query.busy_character_ids_select(time)).all())
    characters = session.scalars(
        world_createion_query.alive_characters_select(time)
        .where(character_active_condition()).order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in busy_ids
            and progression._current_place_id(session, character, time) == place_id]


def _note(key: str) -> str:
    return (f"場面の指定(ジャンルや場面を一言で決めたもの。候補も記録も、すべてこの指定に沿った出来事にする): "
            f"{key}\n")


def _novelize(
    session: Session, record: Event, members: list[Character], key: str, ai: AIClient,
    ideas: idea_context.IdeaContext | None = None, later_events: list[dict] | None = None, *,
    shared_style_extra: str = "", style_extra: str = "",
) -> None:
    involved_ids = set(session.scalars(
        select(EventCharacter.character_id).where(EventCharacter.event_id == record.id)).all())
    involved = [c for c in members if c.id in involved_ids]
    place = session.get(Location, record.location_id) if record.location_id else None
    previous_rows = {}
    for character in involved:
        previous = _latest_event(session, character.id, until=record.start)
        previous_rows[character.name] = (
            _previous_row(session, previous, ai) if previous is not None else "(無し)")
    prompt = "\n".join([
        f"場所: {_dump({'name': place.name, 'kind': place.kind, 'text': place.text} if place else None)}",
        f"時刻: {record.start}〜{record.end}",
        f"場面の指定: {key}",
        f"当事者: {_dump([_sheet(c, record.start) for c in involved]) if involved else '(無し)'}",
        f"当事者それぞれの直前の出来事: {_dump(previous_rows) if previous_rows else '(無し)'}",
        *([f"この時点より後に既に決まっている出来事: {_dump(later_events)}"] if later_events else []),
        f"この出来事の記録: {_dump({'name': record.name, 'text': record.text})}",
        idea_context.prompt_section(ideas.related, ideas.called) if ideas else "",
        f"この出来事を、当事者のうち場面の指定が一番よく伝わる一人を視点人物にした"
        f"{EVENT_NOVEL_TARGET_LETTERS[0]}〜{EVENT_NOVEL_TARGET_LETTERS[1]}字の小説の本文に書き起こしてください。",
    ])
    system_prompt = (_novel_system_prompt(shared_style_extra=shared_style_extra, style_extra=style_extra)
                     if (shared_style_extra or style_extra) else _NOVEL_SYSTEM_PROMPT)
    decided = ai.try_generate_json(
        prompt, _NOVEL_SCHEMA, system=system_prompt, timeout=constants.EVENT_NOVEL_TIMEOUT)
    text = layout_novel_text(decided.get("text") or "")
    if not text:
        print(f"[time_keepr/place] {record.name}(id={record.id}): 本文を小説にできなかったので記録のまま残す")
        return
    record.text = text
    session.commit()
    print(f"[time_keepr/place] {record.name}(id={record.id}): 本文を小説にした({len(text)}字)")


def generate_at(
    session: Session, ai: AIClient, place_id: int, time: Stamp, key: str,
    rng: random.Random | None = None, *, shared_style_extra: str = "", style_extra: str = "",
) -> Event | None:
    """居合わせるサブキャラクターを当事者の候補に、その場所・時刻に `key`(ジャンル・場面)に沿った出来事を起こす。

    `shared_style_extra` / `style_extra` は `_novelize` に渡す(世界ごとの文体の好み)。
    """
    key = (key or "").strip()
    if not key:
        raise ValueError("key(ジャンル・場面の指定)が空")
    place = session.get(Location, place_id)
    if place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")
    if rng is None:
        rng = random.Random(random.randrange(10 ** 9))

    members = _members(session, place_id, time)
    if not members:
        print(f"[time_keepr/place] {place.name}(id={place_id}): "
              f"{format_time(time)} に居合わせて手の空いたサブキャラクターがいない")
        return None
    print(f"[time_keepr/place] {place.name}(id={place_id}) {format_time(time)} の出来事「{key}」: "
          f"居合わせる {', '.join(c.name for c in members)}")
    seeds = event_seed.draw(session, rng)
    print(f"[time_keepr/place] 引いた種: {seeds}")
    record = progression._progress_place(
        session, place_id, members, time, rng, ai, note=_note(key), seeds=seeds, use_story=False)
    if record is None:
        return None
    context = idea_context.gather(session, f"{record.name}\n{record.text}", ai, record.location_id, record.time)
    later_events = progression._later_events(session, record.location_id, members, record.start, ai)
    _novelize(session, record, members, key, ai, context, later_events,
             shared_style_extra=shared_style_extra, style_extra=style_extra)
    idea_context.link(session, record, context.linked)
    session.commit()
    return record
