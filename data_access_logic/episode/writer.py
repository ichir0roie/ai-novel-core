#!/usr/bin/env python3
"""自動生成なので `synced` は立てて確定する(`schema.py` の `Episode.synced` の注記どおり)。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_at
from data_access_logic.episode.models import EpisodeDraft, EpisodeMaterialSerialized, StoryMaterial, TargetEpisode
from data_access_logic.episode.summary import past_episodes
from data_access_logic.event.summary import summarized_events
from data_access_logic.idea.context import gather_ideas
from data_access_logic.idea.links import link
from data_access_logic.query import common_query
from db.schema import ConfirmStatus, Episode, EpisodeCharacter, Event

logger = logging.getLogger(__name__)


def _system_prompt(shared_style_extra: str, style_extra: str) -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
作品・直前の話・書く話(時刻・場所・視点・登場人物・種)などを日本語の見出しを付けた JSON で渡すので、この作品の話を一話ぶん書いてください。
種は作者が決めたこの話の中身です。それを場面まで展開したものを本文にし、種に無い出来事を足さないでください。
直前の話は本文の代わりに概要で渡します。概要の筋をそのまま受け継ぎ、揃える文体を渡したときはそれに揃えてください。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。なぞり直さず、その後の人物として書いてください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{IDEA_CONTEXT_INSTRUCTION}
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}"""


def episode_material(s: Session, ai: AIClient, episode_id: int, past_episode_count: int) -> EpisodeMaterialSerialized:
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
    if not episode.episode_characters:
        raise ValueError(f"話 id={episode_id} の登場人物(episode_character)が空。登場人物を指定してから書く")
    # 要約・候補のアイデアの commit で読み込んだ関連が期限切れになるので、AI を呼ぶ前にマテリアルへ写しておく
    main_episode = TargetEpisode.model_validate(episode)
    story = StoryMaterial.model_validate(episode.story)
    location_id = episode.location_id or episode.story.location_id
    characters = [link.character for link in episode.episode_characters]

    return EpisodeMaterialSerialized(
        story=story,
        main_episode=main_episode,
        past_episodes=past_episodes(s, ai, episode, past_episode_count),
        locations=common_query.location_path(s, location_id)
        if location_id is not None else [],
        cast=cast_at(s, ai, characters, main_episode.start),
        location_events=list(reversed(summarized_events(
            s, ai,
            common_query.events_of_location_select(
                location_id, until=main_episode.start, limit=constants.EPISODE_PLACE_EVENT_LIMIT)
            .where(Event.confirmed == ConfirmStatus.APPROVED)))) if location_id is not None else [],
        later_events=summarized_events(
            s, ai,
            common_query.events_after_select(
                location_id, [character.id for character in characters], main_episode.start,
                limit=constants.LATER_EVENT_LIMIT)),
        ideas=gather_ideas(s, main_episode.key, ai, location_id, main_episode.start),
    )


def write_episode(
    s: Session,
    ai: AIClient,
    episode_id: int,
    model: str,
    effort: str,
    past_episode_count: int = constants.EPISODE_PREVIOUS_LIMIT,
    shared_style_extra: str = "",
    style_extra: str = "",
) -> Episode | None:
    """`model` / `effort` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。"""
    material = episode_material(s, ai, episode_id, past_episode_count)

    prompt = "\n".join([
        material.model_dump_json(indent=2),
        "この話を書いてください。",
    ])
    draft = ai.generate(
        prompt, EpisodeDraft, system=_system_prompt(shared_style_extra, style_extra),
        timeout=constants.EPISODE_TIMEOUT, model=model, effort=effort)
    if draft is None:
        logger.warning(f"{material.story.name}: 本文が得られなかったので見送り")
        return None

    record = s.get_one(Episode, episode_id)
    # 作者が決めた題は残し、空のときだけ本文を書いたときの題で埋める
    record.title = record.title.strip() or draft.title
    record.synced = True
    record.text = draft.text
    s.flush()
    link(s, record, material.ideas.linked)
    s.commit()
    logger.info(f"{material.story.name}「{record.title}」 id={record.id} {record.letters}字")
    return record
