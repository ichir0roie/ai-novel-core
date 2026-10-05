#!/usr/bin/env python3
"""話の材料を組む共通の読み込みと、プロットを書き直す材料(`writing_targets` → 要約を揃える → `episode_material`)。

話の行の読み込み(`load_episode`)・要約を揃える対象(`summary_targets_of`)は、
枠(`framer`)・プロット補完(`plot_completer`)・本文の材料(`brief`)が共に使う。
"""
from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic import constants
from data_access_logic.character.cast import cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.episode.models import (
    EpisodeMaterialSerialized, StoryMaterial, TargetEpisode,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.summary import past_episode_ids, past_episodes
from data_access_logic.event.summary import events_of
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Character, Episode, EpisodeCharacter, Event, Location
from db.stamp import Stamp


class WritingTargets(SummaryTargets):
    # アイデアと照らす語を AI に挙げさせる元(`keywords_of`)
    plot_text: str
    start: Stamp


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


def check_cast(episode: Episode) -> None:
    if not cast_characters(episode):
        raise ValueError(f"話 id={episode.id} の登場人物(episode_character)が空。登場人物を指定してから書く")


def known_locations(s: Session, location_id: int | None) -> list[LocationMaterial]:
    """話の場所の直下にある場所。"""
    if location_id is None:
        return []
    return [LocationMaterial.model_validate(location)
            for location in s.scalars(select(Location).where(Location.parent_id == location_id)).all()]


def location_events_select(location_id: int, start: Stamp) -> Select[Event]:
    return common_query.events_of_location_select(location_id, until=start, limit=constants.EPISODE_PLACE_EVENT_LIMIT)


def later_events_select(location_id: int | None, characters: list[Character], start: Stamp) -> Select[Event]:
    return common_query.events_after_select(
        location_id, [character.id for character in characters], start, limit=constants.LATER_EVENT_LIMIT)


def summary_targets_of(s: Session, episode: Episode, start: Stamp, with_location_events: bool = True) -> SummaryTargets:
    """材料が要約で渡す話・出来事(前の話・登場人物の直近の出来事・場所の直近の出来事・後に決まっている出来事)。"""
    location_id = episode.location_id
    characters = cast_characters(episode)
    location_events = (s.scalars(location_events_select(location_id, start)).all()
                       if with_location_events and location_id is not None else [])
    later_events = s.scalars(later_events_select(location_id, characters, start)).all()
    return SummaryTargets(
        episode_ids=past_episode_ids(s, episode, characters),
        event_ids=[*cast_event_ids(s, characters, start),
                   *(event.id for event in location_events), *(event.id for event in later_events)],
    )


def writing_targets(s: Session, episode_id: int) -> WritingTargets:
    episode = load_episode(s, episode_id)
    check_cast(episode)
    main_episode = TargetEpisode.model_validate(episode)
    targets = summary_targets_of(s, episode, main_episode.start)
    return WritingTargets(**targets.model_dump(), plot_text=main_episode.plot_text, start=main_episode.start)


def episode_material(s: Session, episode_id: int, keywords: list[IdeaDraft]) -> EpisodeMaterialSerialized:
    """要約は揃えてある前提でそのまま読む。`keywords` の語をアイデアと照らし、当たらなかった造語は候補として足す(`resolve_ideas`)。"""
    episode = load_episode(s, episode_id)
    check_cast(episode)
    main_episode = TargetEpisode.model_validate(episode)
    location_id = episode.location_id
    characters = cast_characters(episode)
    return EpisodeMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        past_episodes=past_episodes(s, episode, characters),
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        cast=cast_of(s, characters, main_episode.start),
        mentioned=mentioned_of(mentioned_in(episode), main_episode.start),
        relations=relations_at(s, characters, main_episode.start),
        location_events=list(reversed(events_of(s, location_events_select(location_id, main_episode.start))))
        if location_id is not None else [],
        later_events=events_of(s, later_events_select(location_id, characters, main_episode.start)),
        ideas=resolve_ideas(s, keywords, location_id, main_episode.start),
    )
