#!/usr/bin/env python3
from __future__ import annotations

import random
from collections import defaultdict

from sqlalchemy import select

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import days_between
from data_access_logic.event.progress import progress_place
from data_access_logic.query import common_query, world_createion_query
from data_access_logic.query.base import character_active_condition, location_active_condition
from db.schema import Character, Event, Location, Session, Stamp


def _should_roll(time: Stamp) -> bool:
    return time.day == 1


def _place_roll_probability(session: Session, place_id: int, time: Stamp) -> float:
    last_event = session.scalars(
        common_query.events_of_place_select(place_id, until=time, limit=1)
    ).first()
    if last_event is None:
        return constants.PLACE_PROBABILITY
    months_since = days_between(last_event.time, time) / 30
    if months_since >= constants.PLACE_COOLDOWN_MONTHS:
        return constants.PLACE_PROBABILITY
    return constants.PLACE_PROBABILITY * constants.PLACE_PROBABILITY_COOLDOWN_FACTOR


def current_place_id(session: Session, character: Character, time: Stamp) -> int | None:
    place = session.scalars(
        common_query.character_place_select(character.id, time)).first()
    return place.location_id if place else None


def group_by_place(session: Session, time: Stamp) -> dict[int, list[Character]]:
    grouped: dict[int, list[Character]] = defaultdict(list)

    busy_character_ids = set(session.scalars(
        world_createion_query.busy_character_ids_select(time)).all())

    active_place_ids = set(session.scalars(
        select(Location.id).where(location_active_condition(time))).all())

    characters = session.scalars(
        world_createion_query.alive_characters_select(time)
        .where(character_active_condition())).all()
    for character in characters:
        if character.id in busy_character_ids:
            continue
        place_id = current_place_id(session, character, time)
        if place_id is None or place_id not in active_place_ids:
            continue
        grouped[place_id].append(character)

    return grouped


def generate_random(session: Session, time: Stamp, ai: AIClient) -> list[Event]:
    """常駐ループの出来事は、場所に掛かる作品の本文を進めたい筋書きとして渡す。"""
    if not _should_roll(time):
        return []

    rng = random.Random(random.randrange(10 ** 9))
    created: list[Event] = []

    grouped = group_by_place(session, time)
    total_places = len(grouped)
    for i, (place_id, characters) in enumerate(grouped.items(), start=1):
        probability = _place_roll_probability(session, place_id, time)
        print(f"[time_keepr/event] 場所 {i}/{total_places} id={place_id}: "
              f"人物・対象{len(characters)}件 / ロール確率={probability:.2f}")
        if rng.random() < probability:
            event = progress_place(session, ai, rng, place_id, characters, time, seeds=[], use_story=True)
            if event is not None:
                created.append(event)

    return created
