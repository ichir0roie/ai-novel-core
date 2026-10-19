#!/usr/bin/env python3
"""話の本文を、`claude -p` の生成関数に任せず、このセッションの Claude が自分で書く・直すための材料。

本文の材料(登場人物の直近の出来事・関係、場所の出来事)は話に結んだ登場人物・場所から引くので、
先に `episode_casting` で登場人物・場所を決める材料を読み、Claude が `CastEpisode` で結んでから `episode_brief` を読む
(スキル `episode` / `revise-episode`)。設定は話に結ばず、プロット・話のセッションの行(手番のファイル)・今の本文から AI が挙げた語で引く。
本文は Claude が `CommitEpisode` で確定する。
登場人物を決める材料(`episode_casting`)と人物ごとの関わった話(`character_episodes`)は db だけで読み、概要は作り直さない。
本文の材料も概要・要約を作り直さず、db だけの段(`brief_targets` → AI が語を挙げる → `episode_brief`)に分けてあり、
流れ(`data_access_logic/flows/episode.py`)がつなぐ。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from ai.instructions.past_episodes import PAST_EPISODES_INSTRUCTION, STYLE_SAMPLE_INSTRUCTION
from ai.instructions.sensitive import BIO_ABSTRACTION_INSTRUCTION
from data_access_logic.character.cast import (
    candidate_at, cast_of, casting_candidate_at, mentioned_of, relations_among, secrets_at,
)
from data_access_logic.episode.caster import candidate_characters
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.models import (
    BriefEpisode, CastingEpisode, CharacterEpisodesSerialized, EpisodeBriefSerialized, EpisodeCastingSerialized,
    StoryMaterial,
)
from data_access_logic.episode.material import (
    known_locations, later_events_select, load_episode, location_events_select,
)
from data_access_logic.episode.summary import appearances, past_episodes, recent_appearances, style_samples
from data_access_logic.event.summary import events_of
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.idea.whole import whole_ideas
from data_access_logic.location.reading import location_path_at
from data_access_logic.query import common_query
from data_access_logic.style_preference.extras import read_style_extras
from data_access_logic.material import Material
from db.schema import Character, Episode
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
        IDEA_CONTEXT_INSTRUCTION,
        BIO_ABSTRACTION_INSTRUCTION,
        PAST_EPISODES_INSTRUCTION,
        STYLE_SAMPLE_INSTRUCTION,
        style.style_instruction(read_style_extras(s)),
    ])


def episode_casting(s: Session, episode_id: int) -> EpisodeCastingSerialized:
    """本文の材料を読む前に、プロットから登場人物・場所を決める材料。人物が関わった話は入れない(人物ごとに
    `character_episodes` で読む)。候補は名前と人物像だけにする。"""
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
        candidates=[casting_candidate_at(character, time) for character in candidates],
    )


def character_episodes(s: Session, episode_id: int, character_id: int) -> CharacterEpisodesSerialized:
    """人物がこの話より前に関わった、直近の話を概要だけで。概要は作り直さず、そのときのまま読む。"""
    episode = common_query.get_row(s, Episode, episode_id)
    common_query.get_row(s, Character, character_id)
    return CharacterEpisodesSerialized(appearances=recent_appearances(s, episode, character_id))


class BriefTargets(Material):
    # 設定と照らす語を AI に挙げさせる元(`keywords_of`)。プロット・今の本文の、空でないもの。
    # 話のセッションの行は db に無いので、流れ(`flows/episode.py`)が手番のファイルから足す
    word_sources: list[str]
    start: Stamp


def brief_targets(s: Session, episode_id: int) -> BriefTargets:
    episode = _episode(s, episode_id)
    return BriefTargets(start=episode.start,
                        word_sources=[text for text in (episode.plot_text, episode.main_text) if text.strip()])


def episode_brief(s: Session, episode_id: int, keywords: list[IdeaDraft]) -> EpisodeBriefSerialized:
    """概要・要約は作り直さず、そのまま読む。`keywords` の語をアイデアと照らし、当たったものとその上位を設定に渡す。
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
        style_samples=style_samples(s, episode),
        locations=location_path_at(s, location_id, time) if location_id is not None else [],
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned, time),
        secrets={character.id: secrets_at(s, character, time) for character in [*characters, *mentioned]},
        relations=relations_among(s, characters, time),
        appearances=appearances(s, episode, characters),
        ideas=whole_ideas(s, idea_ids, location_id, time),
        location_events=list(reversed(events_of(s, location_events_select(location_id, time))))
        if location_id is not None else [],
        later_events=events_of(s, later_events_select(location_id, characters, time)),
        guide=_guide(s),
    )
