#!/usr/bin/env python3
"""自動生成なので `synced` は立てて確定する(`schema.py` の `Episode.synced` の注記どおり)。

db だけの段(`writing_targets` → 要約を揃える → `episode_material` → `save_episode`)と、AI だけの段(`episode_draft`)に分けてある。
手元では `write_episode` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.episode.models import (
    EpisodeDraft, EpisodeMaterial, EpisodeMaterialSerialized, StoryMaterial, TargetEpisode,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in
from data_access_logic.episode.summary import past_episode_ids, past_episodes, recent_episodes
from data_access_logic.event.summary import events_of
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.links import link
from data_access_logic.idea.models import IdeaMaterial, IdeaTerm
from data_access_logic.idea.search import keywords_of
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets, refresh
from db.schema import Character, ConfirmStatus, Episode, EpisodeCharacter, Event
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def _system_prompt(shared_style_extra: str, style_extra: str) -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
作品・前の話・書く話(時刻・場所・視点・登場人物・プロット)などを日本語の見出しを付けた JSON で渡すので、この作品の話を一話ぶん書いてください。
プロットは作者が決めたこの話の中身です。それを場面まで展開したものを本文にし、プロットに無い出来事を足さないでください。
直前の話は本文で、それより前の話は概要で渡します。筋をそのまま受け継ぎ、語の選び方・言い回し・地の文とセリフの運びは直前の話の本文に揃えてください。直前の話の文をそのまま写さないでください。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。なぞり直さず、その後の人物として書いてください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{MENTIONED_INSTRUCTION}
{IDEA_CONTEXT_INSTRUCTION}
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}"""


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
        episode_ids=past_episode_ids(s, episode, constants.EPISODE_FULL_TEXT_COUNT),
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
        past_episodes=past_episodes(s, episode, constants.EPISODE_FULL_TEXT_COUNT),
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


def episode_draft(
    ai: AIClient, material: EpisodeMaterial, model: str, effort: str, shared_style_extra: str = "", style_extra: str = "",
) -> EpisodeDraft | None:
    """`model` / `effort` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。"""
    prompt = "\n".join([
        EpisodeMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "この話を書いてください。",
    ])
    return ai.generate(
        prompt, EpisodeDraft, system=_system_prompt(shared_style_extra, style_extra),
        timeout=constants.EPISODE_TIMEOUT, model=model, effort=effort)


def save_episode(s: Session, episode_id: int, draft: EpisodeDraft, ideas: list[IdeaMaterial]) -> Episode:
    record = s.get_one(Episode, episode_id)
    # 作者が決めた題は残し、空のときだけ本文を書いたときの題で埋める
    record.title = record.title.strip() or draft.title
    record.synced = True
    record.main_text = draft.main_text
    s.flush()
    link(s, record, ideas)
    logger.info(f"「{record.title}」 id={record.id} {record.letters}字")
    return record


def write_episode(
    s: Session,
    ai: AIClient,
    episode_id: int,
    model: str,
    effort: str,
    shared_style_extra: str = "",
    style_extra: str = "",
) -> Episode | None:
    targets = writing_targets(s, episode_id)
    refresh(s, ai, targets)
    material = episode_material(s, episode_id, keywords_of(targets.plot_text, ai, targets.start))
    # AI が洗い出した語から足した候補は、この後の生成が失敗しても残す
    s.commit()

    draft = episode_draft(ai, material, model, effort, shared_style_extra, style_extra)
    if draft is None:
        logger.warning(f"{material.story.name}: 本文が得られなかったので見送り")
        return None
    record = save_episode(s, episode_id, draft, material.ideas.linked)
    s.commit()
    return record
