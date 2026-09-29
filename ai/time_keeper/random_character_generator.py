#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy import and_, func, select, union_all

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from data_access_logic.character.generator import generate_character
from data_access_logic.query.base import character_time_condition, location_active_condition
from db.schema import Character, CharacterPlace, Location, Session, Stamp


def _should_roll(time: Stamp) -> bool:
    return time.day == 1


def get_usable_location_q(time: Stamp):
    base_q = (
        select(Location.id)
        .outerjoin(
            CharacterPlace,
            and_(CharacterPlace.location_id == Location.id),
        )
        .outerjoin(
            Character, Character.id == CharacterPlace.character_id
        )
        .where(
            location_active_condition(time),
        )
    )

    q_1 = (
        base_q
        .where(
            Character.id == None,
        )
    )

    q_2 = (
        base_q
        .where(
            character_time_condition(time)
        )
        .group_by(Location.id)
        .having(
            func.count(Character.id.distinct()) < constants.MAX_CHARACTER_PER_LOCATION
        )
    )

    return union_all(q_1, q_2)


def generate_random(session: Session, time: Stamp, ai: AIClient) -> Character | None:
    usable_location_q = get_usable_location_q(time)
    eligible_places = session.scalars(select(Location).where(Location.id.in_(usable_location_q))).all()
    if not eligible_places:
        print(f"[time_keepr/character] 空きのある場所が無いため見送り")
        return None

    for location in eligible_places:
        try_generate_character(
            session, time, location, ai
        )


def try_generate_character(
    session: Session,
    time: Stamp,
    location: Location,
    ai: AIClient,
):
    if not _should_roll(time):
        return None

    seed = random.randrange(10 ** 9)
    rng = random.Random(seed)
    roll = rng.random()
    when = format_time(time)

    if roll >= constants.GENERATION_CHARACTER_PROBABILITY:
        print(f"[time_keepr/character] {when} 判定: "
              f"seed={seed} roll={roll:.4f} >= {constants.GENERATION_CHARACTER_PROBABILITY} → 見送り")
        return None
    print(f"[time_keepr/character] {when} 判定: "
          f"seed={seed} roll={roll:.4f} < {constants.GENERATION_CHARACTER_PROBABILITY} → 生成")

    # 人物か、人物以外の対象か。数の偏りは AI に任せずサイコロで決める。
    person = rng.random() >= constants.NON_PERSON_PROBABILITY
    print(f"[time_keepr/character] {when} 種別判定: {'人物' if person else '人物以外の対象'}")

    return generate_character(session, ai, rng, location.id, time, person)
