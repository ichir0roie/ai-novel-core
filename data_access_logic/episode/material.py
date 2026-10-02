#!/usr/bin/env python3
"""話のプロットを書き直す材料(`writing_targets` → 要約を揃える → `episode_material`)。プロット補完(`plot_completer`)が使う。"""
from __future__ import annotations

import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic import constants
from data_access_logic.character.cast import cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.episode.models import (
    EpisodeMaterialSerialized, StoryMaterial, TargetEpisode,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.summary import past_episode_ids, past_episodes, recent_episodes
from data_access_logic.event.summary import events_of
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaTerm
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Character, ConfirmStatus, Episode, EpisodeCharacter, Event
from db.stamp import Stamp

logger = logging.getLogger(__name__)


class WritingTargets(SummaryTargets):
    # アイデアと照らす語を AI に挙げさせる元(`keywords_of`)
    plot_text: str
    start: Stamp


def _episode(s: Session, episode_id: int) -> Episode:
    episode = s.scalar(
        select(Episode)
        .where(Episode.id == episode_id)
        .options(
            joinedload(Episode.story),
            joinedload(Episode.viewpoint_character),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if episode is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    if not cast_characters(episode):
        raise ValueError(f"話 id={episode_id} の登場人物(episode_character)が空。登場人物を指定してから書く")
    return episode


def _location_id(episode: Episode) -> int | None:
    return episode.location_id or episode.story.location_id


def location_events_select(location_id: int, start: Stamp) -> Select[Event]:
    return (common_query.events_of_location_select(location_id, until=start, limit=constants.EPISODE_PLACE_EVENT_LIMIT)
            .where(Event.confirmed == ConfirmStatus.APPROVED))


def later_events_select(location_id: int | None, characters: list[Character], start: Stamp) -> Select[Event]:
    return common_query.events_after_select(
        location_id, [character.id for character in characters], start, limit=constants.LATER_EVENT_LIMIT)


def writing_targets(s: Session, episode_id: int) -> WritingTargets:
    episode = _episode(s, episode_id)
    main_episode = TargetEpisode.model_validate(episode)
    location_id = _location_id(episode)
    characters = cast_characters(episode)
    location_events = (s.scalars(location_events_select(location_id, main_episode.start)).all()
                       if location_id is not None else [])
    later_events = s.scalars(later_events_select(location_id, characters, main_episode.start)).all()
    return WritingTargets(
        episode_ids=past_episode_ids(s, episode, characters),
        event_ids=[*cast_event_ids(s, characters, main_episode.start),
                   *(event.id for event in location_events), *(event.id for event in later_events)],
        plot_text=main_episode.plot_text,
        start=main_episode.start,
    )


def episode_material(s: Session, episode_id: int, keywords: list[IdeaTerm]) -> EpisodeMaterialSerialized:
    """要約は揃えてある前提でそのまま読む。`keywords` の語をアイデアと照らし、当たらなかった造語は候補として足す(`resolve_ideas`)。"""
    episode = _episode(s, episode_id)
    main_episode = TargetEpisode.model_validate(episode)
    location_id = _location_id(episode)
    characters = cast_characters(episode)
    return EpisodeMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        past_episodes=past_episodes(s, episode, characters),
        recent_episodes=recent_episodes(s, episode),
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        cast=cast_of(s, characters, main_episode.start),
        mentioned=mentioned_of(mentioned_in(episode), main_episode.start),
        relations=relations_at(s, characters, main_episode.start),
        location_events=list(reversed(events_of(s, location_events_select(location_id, main_episode.start))))
        if location_id is not None else [],
        later_events=events_of(s, later_events_select(location_id, characters, main_episode.start)),
        ideas=resolve_ideas(s, keywords, location_id, main_episode.start),
    )
