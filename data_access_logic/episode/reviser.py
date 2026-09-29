#!/usr/bin/env python3
"""手直しなので、本文を書いたときと違い `synced` は変えない。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_at, relations_at
from data_access_logic.episode.models import (
    EpisodeRevisionDraft, EpisodeRevisionMaterialSerialized, RevisedEpisode, StoryMaterial,
)
from data_access_logic.episode.summary import recent_episodes, summarized_episodes
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacter

logger = logging.getLogger(__name__)


def _system_prompt(shared_style_extra: str, style_extra: str) -> str:
    return f"""\
あなたは日本語のライトノベルを直す作家です。
作品・前の話・直す話(今の題・今の本文・登場人物など)を日本語の見出しを付けた JSON で、直す指示をその後に渡すので、指示に沿って今の本文を書き直してください。
指示された箇所だけを字面どおりに直すのではなく、指示の意図と渡した材料(作品・前の話・登場人物・場所)を総合的に判断して、場面の組み立て・順序・会話・描写の配分まで含めて本文を大幅に書き直してかまいません。
話の大筋(誰が何をしてどうなるか)は今の本文から保ってください。
直前の話は本文で、それより前の話は概要で渡します。前の話に出ていない登場人物は、この話が初登場です。
語の選び方・言い回し・地の文とセリフの運びは直前の話の本文に揃えてください。直前の話の文をそのまま写さないでください。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。
{EVENT_AGE_INSTRUCTION}
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}"""


def _revision_material(s: Session, ai: AIClient, episode_id: int) -> EpisodeRevisionMaterialSerialized:
    episode = s.scalar(
        select(Episode)
        .where(Episode.id == episode_id)
        .options(
            joinedload(Episode.story),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if episode is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    if not episode.episode_characters:
        raise ValueError(f"話 id={episode_id} の登場人物(episode_character)が空。登場人物を指定してから直す")
    # 要約の commit で読み込んだ関連が期限切れになるので、AI を呼ぶ前にマテリアルへ写しておく
    main_episode = RevisedEpisode.model_validate(episode)
    story = StoryMaterial.model_validate(episode.story)
    location_id = episode.location_id or episode.story.location_id
    characters = [link.character for link in episode.episode_characters]

    return EpisodeRevisionMaterialSerialized(
        story=story,
        main_episode=main_episode,
        past_episodes=summarized_episodes(s, ai, episode, constants.EPISODE_FULL_TEXT_COUNT),
        recent_episodes=recent_episodes(s, episode),
        locations=common_query.location_path(s, location_id)
        if location_id is not None else [],
        cast=cast_at(s, ai, characters, main_episode.start),
        relations=relations_at(s, characters, main_episode.start),
    )


def _append_instruction_to_key(key: str, instruction: str) -> str:
    """あとで見返せるよう、指示を消さずに積む。"""
    heading = "## 推敲"
    bullet = f"- {instruction.strip()}"
    if heading in key:
        return f"{key.rstrip()}\n{bullet}\n"
    sep = "\n\n" if key.strip() else ""
    return f"{key.rstrip()}{sep}{heading}\n\n{bullet}\n"


def revise_episode(
    s: Session,
    ai: AIClient,
    episode_id: int,
    instruction: str,
    model: str,
    effort: str,
    shared_style_extra: str = "",
    style_extra: str = "",
) -> Episode | None:
    """`model` / `effort` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。"""
    if not instruction.strip():
        raise ValueError("instruction(直す指示)が空")
    material = _revision_material(s, ai, episode_id)

    prompt = "\n".join([
        material.model_dump_json(indent=2),
        f"直す指示: {instruction.strip()}",
    ])
    draft = ai.generate(
        prompt, EpisodeRevisionDraft, system=_system_prompt(shared_style_extra, style_extra),
        timeout=constants.EPISODE_TIMEOUT, model=model, effort=effort)
    if draft is None:
        logger.warning(f"{material.story.name}: 本文が得られなかったので見送り")
        return None

    record = s.get_one(Episode, episode_id)
    record.title = draft.title or record.title
    record.text = draft.text
    record.key = _append_instruction_to_key(record.key, instruction)
    s.commit()
    logger.info(f"推敲「{record.title}」 id={record.id} {record.letters}字")
    return record
