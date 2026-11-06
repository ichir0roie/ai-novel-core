#!/usr/bin/env python3
"""話の材料を組む共通の読み込み。"""
from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic import constants
from data_access_logic.character.cast import cast_event_ids
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.event.models import EventSerialized
from data_access_logic.event.summary import events_of
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Character, Episode, EpisodeCharacter, Event, Location
from db.stamp import Stamp


def load_episode(s: Session, episode_id: int) -> Episode:
    """作品・場所・視点・登場人物(名前だけ出る人物も)を読んだ話の行。"""
    episode = s.scalar(
        select(Episode)
        .where(Episode.id == episode_id)
        .options(
            joinedload(Episode.story),
            joinedload(Episode.location),
            joinedload(Episode.viewpoint_character),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if episode is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    return episode


def known_locations(s: Session, location_id: int | None) -> list[LocationMaterial]:
    """話の場所の直下にある場所。"""
    if location_id is None:
        return []
    return [LocationMaterial.model_validate(location)
            for location in s.scalars(select(Location).where(Location.parent_id == location_id)).all()]


def location_events_select(location_id: int, start: Stamp) -> Select[Event]:
    return common_query.events_of_location_select(location_id, until=start, limit=constants.EPISODE_PLACE_EVENT_LIMIT)


def location_events(s: Session, location_id: int | None, start: Stamp) -> list[EventSerialized]:
    """古い順。"""
    if location_id is None:
        return []
    return list(reversed(events_of(s, location_events_select(location_id, start))))


def later_events_select(location_id: int | None, characters: list[Character], start: Stamp) -> Select[Event]:
    return common_query.events_after_select(
        location_id, [character.id for character in characters], start, limit=constants.LATER_EVENT_LIMIT)


def summary_targets_of(s: Session, episode: Episode, start: Stamp, with_location_events: bool = True) -> SummaryTargets:
    """材料が要約で渡す出来事(登場人物の直近の出来事・場所の直近の出来事・後に決まっている出来事)。"""
    location_id = episode.location_id
    characters = cast_characters(episode)
    location_events = (s.scalars(location_events_select(location_id, start)).all()
                       if with_location_events and location_id is not None else [])
    later_events = s.scalars(later_events_select(location_id, characters, start)).all()
    return SummaryTargets(
        event_ids=[*cast_event_ids(s, characters, start),
                   *(event.id for event in location_events), *(event.id for event in later_events)],
    )
