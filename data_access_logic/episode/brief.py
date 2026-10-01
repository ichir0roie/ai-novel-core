#!/usr/bin/env python3
"""話の本文を、`claude -p` の生成関数に任せず、このセッションの Claude が自分で書く・直すための材料。

材料を読むだけで、書いた本文・登場人物・場所は Claude が `CommitEpisode` などの入口で確定する(スキル `episode` / `revise-episode`)。
db だけの段(`brief_targets` → 要約を揃える → `episode_brief`)に分けてある。
手元では `read_brief` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import age_at, cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.character.models import CastCandidateSerialized
from data_access_logic.character.parameters import parameters_at
from data_access_logic.episode.caster import candidate_characters
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.models import BriefEpisode, EpisodeBriefSerialized, StoryMaterial
from data_access_logic.episode.plot_completer import known_locations
from data_access_logic.episode.summary import past_episode_ids, past_episodes, recent_episodes
from data_access_logic.episode.writer import later_events_select, location_events_select
from data_access_logic.event.summary import events_of
from data_access_logic.query import common_query
from data_access_logic.style_preference.extras import read_style_extras
from data_access_logic.style_preference.form import StyleTarget
from data_access_logic.summary_targets import SummaryTargets, refresh
from db.schema import Episode, EpisodeCharacter


def _episode(s: Session, episode_id: int) -> Episode:
    """登場人物が空でも読む(誰を出すかは、材料を読んだ Claude が決める)。"""
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
    if episode.start is None:
        raise ValueError(f"話 id={episode_id} の時刻(start)が空。歳・直近の出来事を決められないので、先に時刻を入れる")
    return episode


def _location_id(episode: Episode) -> int | None:
    return episode.location_id or episode.story.location_id


def _guide(s: Session) -> str:
    extras = read_style_extras(s, StyleTarget.EPISODE)
    return "\n".join([
        EVENT_AGE_INSTRUCTION,
        MENTIONED_INSTRUCTION,
        style.style_instruction("episode", shared_extra=extras.shared, extra=extras.own),
    ])


def brief_targets(s: Session, episode_id: int) -> SummaryTargets:
    episode = _episode(s, episode_id)
    main_episode = BriefEpisode.model_validate(episode)
    location_id = _location_id(episode)
    characters = cast_characters(episode)
    location_events = (s.scalars(location_events_select(location_id, main_episode.start)).all()
                       if location_id is not None else [])
    later_events = s.scalars(later_events_select(location_id, characters, main_episode.start)).all()
    return SummaryTargets(
        episode_ids=past_episode_ids(s, episode, constants.EPISODE_FULL_TEXT_COUNT),
        event_ids=[*cast_event_ids(s, characters, main_episode.start),
                   *(event.id for event in location_events), *(event.id for event in later_events)],
    )


def episode_brief(s: Session, episode_id: int) -> EpisodeBriefSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    episode = _episode(s, episode_id)
    main_episode = BriefEpisode.model_validate(episode)
    time = main_episode.start
    location_id = _location_id(episode)
    characters = cast_characters(episode)
    mentioned = mentioned_in(episode)
    candidates = candidate_characters(
        s, episode, {character.id for character in [*characters, *mentioned]}, location_id, time)
    return EpisodeBriefSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        past_episodes=past_episodes(s, episode, constants.EPISODE_FULL_TEXT_COUNT),
        recent_episodes=recent_episodes(s, episode),
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        child_locations=known_locations(s, location_id),
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned, time),
        candidates=[CastCandidateSerialized(character=character, age=age_at(character, time),
                                            parameters=parameters_at(character, time))
                    for character in candidates],
        relations=relations_at(s, characters, time),
        location_events=list(reversed(events_of(s, location_events_select(location_id, time))))
        if location_id is not None else [],
        later_events=events_of(s, later_events_select(location_id, characters, time)),
        guide=_guide(s),
    )


def read_brief(s: Session, ai: AIClient, episode_id: int) -> EpisodeBriefSerialized:
    refresh(s, ai, brief_targets(s, episode_id))
    return episode_brief(s, episode_id)
