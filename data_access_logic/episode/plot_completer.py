#!/usr/bin/env python3
"""プロット補完。AI の段(`plot_draft`・`casting_draft`)と db の段を、流れ(`flows/episode.py`)がつなぐ。"""
from __future__ import annotations

import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ai.instructions.materials import IDEA_NOTE, LATER_EVENTS_NOTE, MENTIONED_NOTE, TIME_NOTE
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

_REWRITE_SYSTEM = f"""\
作品・書く話(時刻・場所・視点・登場人物・プロット)などを渡すので、この話のプロットを書き直す。
書き直したプロットは今のプロットと置き換わる。今のプロットにある出来事・人物・場面・台詞・狙いは、一つも落とさずに含め、無い出来事は足さない。
「作者の注文」が null でなければ、今のプロットと合わせて取り入れる。注文が求める出来事は足してよい。
登場人物にいない人物や、書く話の場所より細かい舞台を出すときは、呼び名を付ける。
作品の筋書きと、登場人物の来歴・関係・直近の出来事が、この話の前までの筋。

{LATER_EVENTS_NOTE}

{MENTIONED_NOTE}

{IDEA_NOTE}

{TIME_NOTE}"""

_CASTING_SYSTEM = f"""\
話の材料と、その話の新しいプロット(材料の「書く話」のプロット)を渡すので、新しいプロットに出てくるのに材料に無い人物・舞台を挙げる。
characters は、新しいプロットで台詞や行動のある人物のうち、「登場人物」にも「新しいプロットに名前の出る既知の人物」にもいない人物。群衆や、名前の要らない通りすがりは挙げない。

{IDEA_NOTE}

{TIME_NOTE}"""


def plot_draft(ai: AIClient, material: EpisodeMaterial, order: str | None, model: str, effort: str) -> str:
    request = EpisodePlotRequestSerialized(material=material, order=order)
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "この話のプロットを書き直す。"]),
        EpisodePlotDraft, system=_REWRITE_SYSTEM, style_scope=StyleScope.PLOT, model=model, effort=effort)
    if draft is None:
        raise ValueError("書き直したプロットが得られなかった")
    return draft.plot_text


def save_plot(s: Session, episode_id: int, plot_text: str) -> None:
    s.get_one(Episode, episode_id).plot_text = plot_text
    s.flush()
    save_mentions(s, episode_id)


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
        EpisodeCastingDraft, system=_CASTING_SYSTEM, style_scope=StyleScope.PLOT, model=model, effort=effort)
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


def add_location(s: Session, episode_id: int, candidate: EpisodeLocationCandidateDraft, parent_id: int | None) -> None:
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


def character_draft(candidate: EpisodeCharacterCandidateDraft) -> CharacterForm:
    """候補の人物像と役どころを、作る人物の説明の下書きにする。プロットが固有の名で呼ぶときだけ、その名を作者の名にする
    (役職・あだ名を名にすると、名付けの重なりよけも飛んでしまう)。"""
    return CharacterForm(name=candidate.name or None, text=f"{candidate.text}\n(プロットでの呼び名: {candidate.called})")
