#!/usr/bin/env python3
"""話の本文を、`claude -p` の生成関数に任せず、このセッションの Claude が自分で書く・直すための材料。

本文の材料(登場人物の直近の出来事・関係、場所の出来事)は話に結んだ登場人物・場所から引くので、先に `episode_casting` で
登場人物・場所を決める材料を読み、Claude が `CastEpisode` で結んでから `episode_brief` を読む(スキル `episode` / `revise-episode`)。
本文は Claude が `CommitEpisode` で確定する。
本文の材料は db だけの段(`brief_targets` → 要約を揃える → `episode_brief`)に分けてある。
手元では `read_brief` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from ai.instructions.past_episodes import PAST_EPISODES_INSTRUCTION, STYLE_SAMPLE_INSTRUCTION
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import candidate_at, cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.episode.caster import candidate_characters
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.models import (
    BriefEpisode, CastingEpisode, EpisodeBriefSerialized, EpisodeCastingSerialized, StoryMaterial,
)
from data_access_logic.episode.plot_completer import known_locations
from data_access_logic.episode.summary import appearances, past_episode_ids, past_episodes, recent_episodes
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
        PAST_EPISODES_INSTRUCTION,
        STYLE_SAMPLE_INSTRUCTION,
        style.style_instruction("episode", shared_extra=extras.shared, extra=extras.own),
    ])


def episode_casting(s: Session, episode_id: int) -> EpisodeCastingSerialized:
    """本文の材料を読む前に、プロットから登場人物・場所を決める材料。要約を使わないので AI は呼ばない。"""
    episode = _episode(s, episode_id)
    main_episode = CastingEpisode.model_validate(episode)
    time = main_episode.start
    location_id = _location_id(episode)
    characters = cast_characters(episode)
    mentioned = mentioned_in(episode)
    candidates = candidate_characters(
        s, episode, {character.id for character in [*characters, *mentioned]}, location_id, time)
    return EpisodeCastingSerialized(
        main_episode=main_episode,
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        child_locations=known_locations(s, location_id),
        cast=[candidate_at(character, time) for character in characters],
        mentioned=[candidate_at(character, time) for character in mentioned],
        candidates=[candidate_at(character, time) for character in candidates],
        appearances=appearances(s, episode, [*characters, *mentioned]),
    )


def brief_targets(s: Session, episode_id: int) -> SummaryTargets:
    episode = _episode(s, episode_id)
    main_episode = BriefEpisode.model_validate(episode)
    location_id = _location_id(episode)
    characters = cast_characters(episode)
    location_events = (s.scalars(location_events_select(location_id, main_episode.start)).all()
                       if location_id is not None else [])
    later_events = s.scalars(later_events_select(location_id, characters, main_episode.start)).all()
    return SummaryTargets(
        episode_ids=past_episode_ids(s, episode, characters),
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
    return EpisodeBriefSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        past_episodes=past_episodes(s, episode, characters),
        recent_episodes=recent_episodes(s, episode),
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned_in(episode), time),
        relations=relations_at(s, characters, time),
        appearances=appearances(s, episode, characters),
        location_events=list(reversed(events_of(s, location_events_select(location_id, time))))
        if location_id is not None else [],
        later_events=events_of(s, later_events_select(location_id, characters, time)),
        guide=_guide(s),
    )


def read_brief(s: Session, ai: AIClient, episode_id: int) -> EpisodeBriefSerialized:
    refresh(s, ai, brief_targets(s, episode_id))
    return episode_brief(s, episode_id)
