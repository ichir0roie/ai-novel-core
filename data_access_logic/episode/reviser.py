#!/usr/bin/env python3
"""手直しなので、本文を書いたときと違い `synced` は変えない。

db だけの段(`revision_targets` → 要約を揃える → `revision_material` → `save_revision`)と、AI だけの段(`revision_draft`)に分けてある。
手元では `revise_episode` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.episode.models import (
    EpisodeRevisionDraft, EpisodeRevisionMaterial, EpisodeRevisionMaterialSerialized, RevisedEpisode, StoryMaterial,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in, save_mentions
from data_access_logic.episode.summary import past_episode_ids, past_episodes, recent_episodes
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets, refresh
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
{MENTIONED_INSTRUCTION}
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}"""


def _episode(s: Session, episode_id: int) -> Episode:
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
    if not cast_characters(episode):
        raise ValueError(f"話 id={episode_id} の登場人物(episode_character)が空。登場人物を指定してから直す")
    return episode


def revision_targets(s: Session, episode_id: int) -> SummaryTargets:
    episode = _episode(s, episode_id)
    main_episode = RevisedEpisode.model_validate(episode)
    return SummaryTargets(
        episode_ids=past_episode_ids(s, episode, cast_characters(episode), constants.EPISODE_FULL_TEXT_COUNT),
        event_ids=cast_event_ids(s, cast_characters(episode), main_episode.start),
    )


def revision_material(s: Session, episode_id: int) -> EpisodeRevisionMaterialSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    episode = _episode(s, episode_id)
    main_episode = RevisedEpisode.model_validate(episode)
    location_id = episode.location_id or episode.story.location_id
    characters = cast_characters(episode)
    return EpisodeRevisionMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        past_episodes=past_episodes(s, episode, characters, constants.EPISODE_FULL_TEXT_COUNT),
        recent_episodes=recent_episodes(s, episode),
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        cast=cast_of(s, characters, main_episode.start),
        mentioned=mentioned_of(mentioned_in(episode), main_episode.start),
        relations=relations_at(s, characters, main_episode.start),
    )


def _append_instruction_to_plot(plot_text: str, instruction: str) -> str:
    """あとで見返せるよう、指示を消さずに積む。"""
    heading = "## 推敲"
    bullet = f"- {instruction.strip()}"
    if heading in plot_text:
        return f"{plot_text.rstrip()}\n{bullet}\n"
    sep = "\n\n" if plot_text.strip() else ""
    return f"{plot_text.rstrip()}{sep}{heading}\n\n{bullet}\n"


def revision_draft(
    ai: AIClient, material: EpisodeRevisionMaterial, instruction: str, model: str, effort: str,
    shared_style_extra: str = "", style_extra: str = "",
) -> EpisodeRevisionDraft | None:
    """`model` / `effort` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。"""
    prompt = "\n".join([
        EpisodeRevisionMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        f"直す指示: {instruction.strip()}",
    ])
    return ai.generate(
        prompt, EpisodeRevisionDraft, system=_system_prompt(shared_style_extra, style_extra),
        timeout=constants.EPISODE_TIMEOUT, model=model, effort=effort)


def save_revision(s: Session, episode_id: int, draft: EpisodeRevisionDraft, instruction: str) -> Episode:
    record = s.get_one(Episode, episode_id)
    record.title = draft.title or record.title
    record.main_text = draft.main_text
    record.plot_text = _append_instruction_to_plot(record.plot_text, instruction)
    s.flush()
    save_mentions(s, episode_id)
    logger.info(f"推敲「{record.title}」 id={record.id} {record.letters}字")
    return record


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
    if not instruction.strip():
        raise ValueError("instruction(直す指示)が空")
    refresh(s, ai, revision_targets(s, episode_id))
    material = revision_material(s, episode_id)
    draft = revision_draft(ai, material, instruction, model, effort, shared_style_extra, style_extra)
    if draft is None:
        logger.warning(f"{material.story.name}: 本文が得られなかったので見送り")
        return None
    record = save_revision(s, episode_id, draft, instruction)
    s.commit()
    return record
