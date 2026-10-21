#!/usr/bin/env python3
"""プロット補完。本文は書かない(本文はスキル `episode` でこのセッションの Claude が書く)。

材料は `material.writing_targets` → 要約を揃える → `material.episode_material`。
AI だけの段(`plot_draft`・`casting_draft`)と db だけの段(`save_plot`・`material.known_locations`・`add_cast_member`・`add_location`)に分けてあり、
流れ(`data_access_logic/flows/episode.py`)がつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import mentioned_of
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.models import MentionedMaterial
from data_access_logic.episode.models import (
    EpisodeCastingDraft, EpisodeCastingRequestSerialized, EpisodeCharacterCandidateDraft, EpisodeLocationCandidateDraft,
    EpisodeMaterial, EpisodePlotDraft, EpisodePlotRequestSerialized,
)
from data_access_logic.episode.mentions import mentioned_in, save_mentions
from data_access_logic.episode.material import load_episode
from data_access_logic.location.models import LocationMaterial
from db.schema import Character, Episode, EpisodeCharacter, Location, StyleScope
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def plot_draft(ai: AIClient, material: EpisodeMaterial, order: str | None, model: str, effort: str) -> str:
    request = EpisodePlotRequestSerialized(material=material, order=order)
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "この話のプロットを書き直す。"]),
        EpisodePlotDraft, instruction=StyleScope.PLOT_REWRITE,
        model=model, effort=effort, story_id=material.story.id)
    if draft is None:
        raise ValueError("書き直したプロットが得られなかった")
    return draft.plot_text


def save_plot(s: Session, episode_id: int, plot_text: str) -> Episode:
    record = s.get_one(Episode, episode_id)
    record.plot_text = plot_text
    s.flush()
    save_mentions(s, episode_id)
    return record


def known_characters(s: Session, episode_id: int, time: Stamp) -> list[MentionedMaterial]:
    """登場人物でなく、今のプロット・本文に名前が出る人物(`save_mentions` で拾った人物)。"""
    return list(mentioned_of(mentioned_in(load_episode(s, episode_id)), time))


def casting_draft(
    ai: AIClient, material: EpisodeMaterial, plot_text: str, known: list[LocationMaterial],
    known_people: list[MentionedMaterial], model: str, effort: str,
) -> EpisodeCastingDraft | None:
    request = EpisodeCastingRequestSerialized(
        material=material, plot_text=plot_text, known_locations=known, known_characters=known_people)
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "新しいプロットに出てくるのに材料に無い人物・舞台を挙げる。"]),
        EpisodeCastingDraft, instruction=StyleScope.PLOT_CASTING,
        model=model, effort=effort, story_id=material.story.id)
    if draft is None:
        logger.warning("人物・舞台の候補が得られなかったので、プロットの書き直しだけにする")
    return draft


def add_cast_member(s: Session, episode_id: int, character_id: int) -> None:
    """名前だけ出る人物(`mentioned`)の行があれば、登場人物の行に置き換える。"""
    record = s.get_one(Character, character_id)
    s.execute(delete(EpisodeCharacter).where(
        EpisodeCharacter.episode_id == episode_id, EpisodeCharacter.character_id == character_id))
    s.add(EpisodeCharacter(episode_id=episode_id, character_id=character_id))
    s.flush()
    logger.info(f"{record.name}(id={record.id})を登場人物に足した")


def add_location(s: Session, episode_id: int, candidate: EpisodeLocationCandidateDraft, parent_id: int | None) -> Location:
    location = Location(
        parent_id=parent_id,
        name=candidate.name,
        kind=candidate.kind,
        text=candidate.text,
        environment=candidate.environment or None,
    )
    s.add(location)
    s.flush()
    s.get_one(Episode, episode_id).location_id = location.id
    s.flush()
    logger.info(f"舞台 {location.name}(id={location.id})を足し、話の場所にした")
    return location


def character_draft(candidate: EpisodeCharacterCandidateDraft) -> CharacterForm:
    """候補の人物像と役どころを、作る人物の説明の下書きにする。プロットが固有の名で呼ぶときだけ、その名を作者の名にする
    (役職・あだ名を名にすると、名付けの重なりよけも飛んでしまう)。"""
    return CharacterForm(name=candidate.name or None, text=f"{candidate.text}\n(プロットでの呼び名: {candidate.called})")
