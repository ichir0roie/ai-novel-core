from typing import Sequence
from db.schema import *
from data_access_logic.query import common_query


def location_time_condition(time: Stamp):
    return and_(
        or_(Location.start.is_(None), Location.start <= time),
        or_(
            Location.end > time,
            Location.end.is_(None)
        )
    )


def location_active_condition(time: Stamp):
    return and_(
        location_time_condition(time),
        Location.active_random_generation.is_(True)
    )


def character_active_condition():
    return Character.main_character.is_(False)


def character_time_condition(time: Stamp):
    return and_(
        or_(CharacterPlace.start.is_(None), CharacterPlace.start <= time),
        or_(
            CharacterPlace.end > time,
            CharacterPlace.end.is_(None)
        )
    )


def story_time_condition(time: Stamp):
    return and_(
        or_(Story.start.is_(None), Story.start <= time),
        or_(Story.end.is_(None), Story.end > time),
    )
