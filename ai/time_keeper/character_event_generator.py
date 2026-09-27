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
from ai.time_keeper import event_seed, event_summary, idea_context
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import add_days, add_years, format_time
from data_access_logic.query import common_query
from data_access_logic.query.base import character_active_condition
from db.schema import Character, Event, EventCharacter, Location, Session, Stamp

def _novel_system_prompt(*, shared_style_extra: str = "", style_extra: str = "") -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
ある人物(主役)の身に起きた出来事の記録と、場所・当事者・主役の直前の出来事を渡すので、この出来事を小説の本文に書き起こしてください。
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


def _finished(event: Event) -> Stamp:
    return event.end or event.start or event.time


def _latest_event(session: Session, character_id: int, until: Stamp | None = None) -> Event | None:
    return session.scalars(common_query.latest_character_event_select(character_id, until=until)).first()


def _busy_at(session: Session, character: Character, time: Stamp) -> bool:
    return session.scalars(
        common_query.character_events_overlapping_select(character.id, time)).first() is not None


def _time_at_age(character: Character, age: int, rng: random.Random) -> Stamp | None:
    if character.start is None:
        return None
    return add_days(add_years(character.start, age), rng.randint(0, 364))


def _first_base(character: Character, rng: random.Random) -> Stamp | None:
    if character.start is None:
        return None
    return add_years(character.start, rng.randint(*constants.FIRST_EVENT_AGE_YEARS))


def _place_of(
    session: Session, character: Character, time: Stamp,
) -> tuple[int, list[Character]] | None:
    for place_id, members in progression._group_by_place(session, time).items():
        if any(member.id == character.id for member in members):
            return place_id, members
    return None


def _free_after(session: Session, character: Character, time: Stamp) -> bool:
    """人物ごとに時間が進むので、先の出来事と重ねない。"""
    latest = _latest_event(session, character.id)
    return latest is None or _finished(latest) <= time


def _previous_row(session: Session, previous: Event | None, ai: AIClient) -> dict | str:
    """本文は写させないよう要約で渡す。"""
    # 場所は noload の関連なので、commit で期限切れになる前(読んだ直後)に組んでおく
    if previous is None:
        return "(無し。主役の最初の出来事)"
    row = {"name": previous.name,
           "start": str(previous.start) if previous.start else None,
           "end": str(previous.end) if previous.end else None,
           "place": previous.location.name if previous.location else None}
    text = previous.text
    summary = event_summary.summarize(session, previous, ai)
    return {**row, "summary": summary} if summary else {**row, "text": text}


def _note(character: Character, previous_row: dict | str) -> str:
    focus = {"character_id": character.id, "name": character.name}
    return (f"この出来事の主役(主役の身に起きる次の出来事として考え、当事者に必ず含める): {focus}\n"
            f"主役の直前の出来事(これが終わった後に起きる出来事として考える): {previous_row}\n")


def _sheet(character: Character, time: Stamp) -> dict:
    parameters = character.parameters_at(time)
    return {"name": character.name, "kind": character.kind, "age": progression.age_at(character, time),
            **{column: parameters[column] for column in (
                "family_name", "sex", "first_person", "second_person", "third_person", "tone", "dialect")},
            "text": character.text}


def _novelize(
    session: Session, record: Event, focus: Character, participants: list[Character],
    previous_row: dict | str, ai: AIClient, ideas: idea_context.IdeaContext | None = None,
    later_events: list[dict] | None = None, *,
    shared_style_extra: str = "", style_extra: str = "",
) -> None:
    involved_ids = set(session.scalars(
        select(EventCharacter.character_id).where(EventCharacter.event_id == record.id)).all())
    place = session.get(Location, record.location_id) if record.location_id else None
    others = [_sheet(c, record.start) for c in participants if c.id in involved_ids and c.id != focus.id]
    prompt = "\n".join([
        f"場所: {_dump({'name': place.name, 'kind': place.kind, 'text': place.text} if place else None)}",
        f"時刻: {record.start}〜{record.end}",
        f"主役: {_dump(_sheet(focus, record.start))}",
        f"ほかの当事者: {_dump(others) if others else '(無し)'}",
        f"主役の直前の出来事: {_dump(previous_row)}",
        *([f"この時点より後に既に決まっている出来事: {_dump(later_events)}"] if later_events else []),
        f"この出来事の記録: {_dump({'name': record.name, 'text': record.text})}",
        idea_context.prompt_section(ideas.related, ideas.called) if ideas else "",
        f"この出来事を、{focus.name}を視点人物にした"
        f"{EVENT_NOVEL_TARGET_LETTERS[0]}〜{EVENT_NOVEL_TARGET_LETTERS[1]}字の小説の本文に書き起こしてください。",
    ])
    system_prompt = (_novel_system_prompt(shared_style_extra=shared_style_extra, style_extra=style_extra)
                     if (shared_style_extra or style_extra) else _NOVEL_SYSTEM_PROMPT)
    decided = ai.try_generate_json(
        prompt, _NOVEL_SCHEMA, system=system_prompt, timeout=constants.EVENT_NOVEL_TIMEOUT)
    text = layout_novel_text(decided.get("text") or "")
    if not text:
        print(f"[time_keepr/daily] {record.name}(id={record.id}): 本文を小説にできなかったので記録のまま残す")
        return
    record.text = text
    session.commit()
    print(f"[time_keepr/daily] {record.name}(id={record.id}): 本文を小説にした({len(text)}字)")


def generate_next(
    session: Session, ai: AIClient, rng: random.Random | None = None, character_id: int | None = None,
    age: int | None = None, *, shared_style_extra: str = "", style_extra: str = "",
) -> Event | None:
    """age を渡すと、直前の出来事の後ではなくその歳のうちに起こす。既にある後の出来事の間に差し込むことになる。

    `shared_style_extra` / `style_extra` は `_novelize` に渡す(世界ごとの文体の好み)。
    """
    if rng is None:
        rng = random.Random(random.randrange(10 ** 9))
    query = select(Character).where(character_active_condition()).order_by(Character.id)
    if character_id is not None:
        query = query.where(Character.id == character_id)
    candidates = list(session.scalars(query).all())
    rng.shuffle(candidates)

    for character in candidates:
        if age is None:
            previous = _latest_event(session, character.id)
            base = _finished(previous) if previous is not None else _first_base(character, rng)
            if base is None:
                continue
            time = add_days(base, rng.randint(*constants.NEXT_EVENT_GAP_DAYS))
        else:
            time = _time_at_age(character, age, rng)
            if time is None:
                continue
            if _busy_at(session, character, time):
                print(f"[time_keepr/daily] {character.name}(id={character.id}): "
                      f"{format_time(time)} は別の出来事の最中なので選び直す")
                continue
            previous = _latest_event(session, character.id, until=time)
        found = _place_of(session, character, time)
        if found is None:
            print(f"[time_keepr/daily] {character.name}(id={character.id}): "
                  f"{format_time(time)} に出来事の対象にならないので選び直す")
            continue
        place_id, members = found
        participants = [character, *(
            member for member in members
            if member.id != character.id and (
                _free_after(session, member, time) if age is None else not _busy_at(session, member, time)))]
        print(f"[time_keepr/daily] {character.name}(id={character.id}) の次の出来事: "
              f"{format_time(time)} 場所id={place_id} / "
              + (f"直前: {previous.name}" if previous is not None else "最初の出来事"))
        previous_row = _previous_row(session, previous, ai)
        seeds = event_seed.draw(session, rng)
        print(f"[time_keepr/daily] 引いた種: {seeds}")
        record = progression._progress_place(
            session, place_id, participants, time, rng, ai,
            focus=character, note=_note(character, previous_row), seeds=seeds, use_story=False)
        if record is not None:
            context = idea_context.gather(session, f"{record.name}\n{record.text}", ai, record.location_id, record.time)
            later_events = progression._later_events(session, record.location_id, participants, record.start, ai)
            _novelize(session, record, character, participants, previous_row, ai, context, later_events,
                     shared_style_extra=shared_style_extra, style_extra=style_extra)
            idea_context.link(session, record, context.linked)
            session.commit()
        return record

    print("[time_keepr/daily] 出来事を起こせるサブキャラクターがいない")
    return None
