#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy import select

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import add_days, add_years, format_time
from ai.time_keeper.event_progression_generator import group_by_place
from data_access_logic.event.novelist import novelize_event
from data_access_logic.event.progress import progress_place
from data_access_logic.event_seed.extractor import draw as draw_seeds
from data_access_logic.query import common_query
from data_access_logic.query.base import character_active_condition
from db.schema import Character, Event, Session, Stamp


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
    for place_id, members in group_by_place(session, time).items():
        if any(member.id == character.id for member in members):
            return place_id, members
    return None


def _free_after(session: Session, character: Character, time: Stamp) -> bool:
    """人物ごとに時間が進むので、先の出来事と重ねない。"""
    latest = _latest_event(session, character.id)
    return latest is None or _finished(latest) <= time


def generate_next(
    session: Session, ai: AIClient, rng: random.Random | None = None, character_id: int | None = None,
    age: int | None = None, shared_style_extra: str = "", style_extra: str = "",
) -> Event | None:
    """age を渡すと、直前の出来事の後ではなくその歳のうちに起こす。既にある後の出来事の間に差し込むことになる。

    `shared_style_extra` / `style_extra` は `novelize_event` に渡す(世界ごとの文体の好み)。
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
        seeds = draw_seeds(session, rng)
        print(f"[time_keepr/daily] 引いた種: {seeds}")
        record = progress_place(session, ai, rng, place_id, participants, time, seeds, focus=character)
        if record is not None:
            novelize_event(session, ai, record.id, focus_character_id=character.id,
                           shared_style_extra=shared_style_extra, style_extra=style_extra)
        return record

    print("[time_keepr/daily] 出来事を起こせるサブキャラクターがいない")
    return None
