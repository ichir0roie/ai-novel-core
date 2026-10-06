#!/usr/bin/env python3
"""話の本文を、`claude -p` の生成関数に任せず、このセッションの Claude が自分で書く・直すための材料。

本文の材料(登場人物の直近の出来事・関係、場所の出来事)は話に結んだ登場人物・場所から引くので、
先に `episode_casting` で登場人物・場所を決める材料を読み、Claude が `CastEpisode` で結んでから `episode_brief` を読む
(スキル `episode` / `revise-episode`)。設定は話に結ばず、プロット・話のセッションの行・今の本文から AI が挙げた語で引く。
本文は Claude が `CommitEpisode` で確定する。
どちらの材料も db だけの段(`casting_targets` / `brief_targets` → 要約を揃える(本文の材料は、語も挙げる) →
`episode_casting` / `episode_brief`)に分けてある。
流れ(`data_access_logic/flows/episode.py`)がつなぐ。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from ai.instructions.past_episodes import PAST_EPISODES_INSTRUCTION, STYLE_SAMPLE_INSTRUCTION
from data_access_logic.character.cast import candidate_at, cast_of, mentioned_of, relations_at, secrets_at
from data_access_logic.episode.caster import candidate_characters
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.models import (
    BriefEpisode, CastingEpisode, EpisodeBriefSerialized, EpisodeCastingSerialized, StoryMaterial,
)
from data_access_logic.episode.material import (
    known_locations, later_events_select, load_episode, location_events_select, summary_targets_of,
)
from data_access_logic.episode.summary import appearances, past_episodes, recent_episodes
from data_access_logic.event.summary import events_of
from data_access_logic.episode_session.turns import session_select
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.idea.whole import whole_ideas
from data_access_logic.location.reading import location_path_at
from data_access_logic.query import common_query
from data_access_logic.style_preference.extras import read_style_extras
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Episode
from db.stamp import Stamp


def _episode(s: Session, episode_id: int) -> Episode:
    """登場人物が空でも読む(誰を出すかは、材料を読んだ Claude が決める)。"""
    episode = load_episode(s, episode_id)
    if episode.start is None:
        raise ValueError(f"話 id={episode_id} の時刻(start)が空。歳・直近の出来事を決められないので、先に時刻を入れる")
    return episode


def _guide(s: Session) -> str:
    return "\n".join([
        EVENT_AGE_INSTRUCTION,
        MENTIONED_INSTRUCTION,
        PAST_EPISODES_INSTRUCTION,
        STYLE_SAMPLE_INSTRUCTION,
        style.style_instruction(read_style_extras(s)),
    ])


def casting_targets(s: Session, episode_id: int) -> SummaryTargets:
    """登場人物・名前だけ出る人物が関わった話(`episode_casting` が概要を付ける話)。"""
    episode = _episode(s, episode_id)
    links = appearances(s, episode, [*cast_characters(episode), *mentioned_in(episode)])
    return SummaryTargets(episode_ids=[link.episode.id for link in links])


def episode_casting(s: Session, episode_id: int) -> EpisodeCastingSerialized:
    """本文の材料を読む前に、プロットから登場人物・場所を決める材料。要約は揃えてある前提でそのまま読む。"""
    episode = _episode(s, episode_id)
    main_episode = CastingEpisode.model_validate(episode)
    time = main_episode.start
    location_id = episode.location_id
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


class BriefTargets(SummaryTargets):
    # 設定と照らす語を AI に挙げさせる元(`keywords_of`)。プロット・話のセッションの行・今の本文の、空でないもの
    word_sources: list[str]
    start: Stamp


def _word_sources(s: Session, episode: Episode) -> list[str]:
    rows = s.scalars(session_select(episode.id)).all()
    session = "\n".join(text for row in rows
                        for text in (row.request, row.thought, row.action, row.speech, row.aim) if text)
    return [text for text in (episode.plot_text, session, episode.main_text) if text.strip()]


def brief_targets(s: Session, episode_id: int) -> BriefTargets:
    episode = _episode(s, episode_id)
    targets = summary_targets_of(s, episode, episode.start)
    return BriefTargets(**targets.model_dump(), word_sources=_word_sources(s, episode), start=episode.start)


def episode_brief(s: Session, episode_id: int, keywords: list[IdeaDraft]) -> EpisodeBriefSerialized:
    """要約は揃えてある前提でそのまま読む。`keywords` の語をアイデアと照らし、当たったものとその上位・下位を設定に渡す。
    当たらなかった造語は候補として足し、設定に入れる(`resolve_ideas`)。"""
    episode = _episode(s, episode_id)
    main_episode = BriefEpisode.model_validate(episode)
    time = main_episode.start
    location_id = episode.location_id
    characters = cast_characters(episode)
    mentioned = mentioned_in(episode)
    context = resolve_ideas(s, keywords, location_id, time)
    idea_ids = [*(related.idea.id for related in context.related), *(candidate.id for candidate in context.candidates)]
    return EpisodeBriefSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        past_episodes=past_episodes(s, episode, characters),
        recent_episodes=recent_episodes(s, episode),
        locations=location_path_at(s, location_id, time) if location_id is not None else [],
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned, time),
        secrets={character.id: secrets_at(s, character, time) for character in [*characters, *mentioned]},
        relations=relations_at(s, characters, time),
        appearances=appearances(s, episode, characters),
        ideas=whole_ideas(s, idea_ids, location_id, time),
        location_events=list(reversed(events_of(s, location_events_select(location_id, time))))
        if location_id is not None else [],
        later_events=events_of(s, later_events_select(location_id, characters, time)),
        guide=_guide(s),
    )
