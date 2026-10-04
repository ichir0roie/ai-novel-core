#!/usr/bin/env python3
"""プロット補完。本文は書かない(本文はスキル `episode` でこのセッションの Claude が書く)。

材料は `material.writing_targets` → 要約を揃える → `material.episode_material`。
AI だけの段(`plot_draft`・`casting_draft`)と db だけの段(`save_plot`・`material.known_locations`・`add_cast_member`・`add_location`)に分けてあり、
手元では `complete_plot` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from ai.instructions.past_episodes import PAST_EPISODES_INSTRUCTION
from ai.instructions.plot import PLOT_FORMAT_INSTRUCTION
from ai.instructions.naming import PLACE_NAMING_INSTRUCTION
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import mentioned_of
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.generator import generate_character
from data_access_logic.character.models import MentionedMaterial
from data_access_logic.episode.models import (
    EpisodeCastingDraft, EpisodeCastingRequestSerialized, EpisodeCharacterCandidateDraft, EpisodeLocationCandidateDraft,
    EpisodeMaterial, EpisodePlotDraft, EpisodePlotRequestSerialized,
)
from data_access_logic.episode.mentions import mentioned_in, save_mentions
from data_access_logic.episode.material import episode_material, known_locations, load_episode, writing_targets
from data_access_logic.idea.search import keywords_of
from data_access_logic.location.models import LocationMaterial
from data_access_logic.summary_targets import refresh
from db.schema import Character, Episode, EpisodeCharacter, Location
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_PLOT_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルを書く作家です。
作品・前の話・書く話(時刻・場所・視点・登場人物・プロット)などを日本語の見出しを付けた JSON で渡すので、この話のプロットを書き直してください。
書き直したプロットは今のプロットとそっくり置き換わり、本文はそれだけを元に書きます。今のプロットにある出来事・人物・場面・狙いは、一つも落とさずに書き直したプロットへ含めてください。
{PLOT_FORMAT_INSTRUCTION}
今のプロットに無い出来事は足さないでください。
「作者の注文」が null でなければ、今のプロットに加えて作者が新しいプロットに望むこと(展開・焦点・雰囲気など)です。今のプロットと合わせて取り入れてください。注文が求める出来事は足してかまいません。
場面に要るなら、登場人物にいない人物や、書く話の場所より細かい舞台(店・屋敷・部屋など)を出してかまいません。その人物・舞台には呼び名を付けてください。
{PAST_EPISODES_INSTRUCTION}
登場人物それぞれの直近の出来事は、この話の前に済んだことです。なぞり直さず、その後の人物として書いてください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{MENTIONED_INSTRUCTION}
{IDEA_CONTEXT_INSTRUCTION}"""

_CASTING_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルの設定を整える作家です。
話の材料と、その話の新しいプロットを日本語の見出しを付けた JSON で渡すので、新しいプロットに出てくるのに材料に無い人物・舞台を挙げてください。材料の「書く話」のプロットは、新しいプロットです。
characters には、新しいプロットで台詞や行動のある人物のうち、登場人物にいない人物を挙げてください。群衆や、名前の要らない通りすがりは挙げません。
「新しいプロットに名前の出る既知の人物」は、もういる人物なので挙げません。
人物の説明は、材料の作品・場所・時刻に馴染むように書いてください。
location には、新しいプロットの主な舞台が書く話の場所より細かい場所で、「この場所の中の既知の場所」にも無いときだけ、その舞台を書いてください。
location の名前は次の基準で名づけます。
{PLACE_NAMING_INSTRUCTION}"""


def plot_draft(ai: AIClient, material: EpisodeMaterial, order: str | None, model: str, effort: str) -> str:
    request = EpisodePlotRequestSerialized(material=material, order=order)
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "この話のプロットを書き直してください。"]),
        EpisodePlotDraft, system=_PLOT_SYSTEM_PROMPT,
        model=model, effort=effort)
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
        "\n".join([request.model_dump_json(indent=2), "新しいプロットに出てくるのに材料に無い人物・舞台を挙げてください。"]),
        EpisodeCastingDraft, system=_CASTING_SYSTEM_PROMPT,
        model=model, effort=effort)
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


def add_characters(
    s: Session, ai: AIClient, episode_id: int, candidates: list[EpisodeCharacterCandidateDraft],
    location_id: int | None, time: Stamp, plot_text: str,
) -> None:
    rng = random.Random()
    for candidate in candidates:
        # generate_character は一人ごとに commit するので、途中で止まっても作った人物は残る
        record = generate_character(
            s, ai, rng, location_id, time, True, character_draft(candidate), plot_text)
        if record is None:
            logger.warning(f"「{candidate.called}」の人物が得られなかったので足さない")
            continue
        add_cast_member(s, episode_id, record.id)
        s.commit()


def complete_plot(
    s: Session, ai: AIClient, episode_id: int, order: str | None, model: str, effort: str,
) -> Episode:
    """今のプロットを核に、`order`(作者の注文。無ければ None)も取り入れて、本文全体を場面に割ったプロットを書き直させ、
    それでプロットをそっくり置き換える(今のプロットの中身は書き直したプロットに含めさせる)。
    書き直したプロットに出るのに材料に無い人物は作って登場人物に足し、話の場所より細かい舞台はその場所の下に作って話の場所にする。
    `model` / `effort` はプロットの書き直しと候補の呼び出しに渡す(人物を作る呼び出しは人物の生成の既定のまま)。"""
    targets = writing_targets(s, episode_id)
    refresh(s, ai, targets)
    material = episode_material(s, episode_id, keywords_of(targets.plot_text, ai, targets.start))
    s.commit()
    plot_text = plot_draft(ai, material, order, model, effort)
    save_plot(s, episode_id, plot_text)
    s.commit()

    location_id = material.locations[-1].id if material.locations else None
    casting = casting_draft(
        ai, material, plot_text, known_locations(s, location_id),
        known_characters(s, episode_id, material.main_episode.start), model, effort)
    if casting is not None and casting.characters:
        add_characters(s, ai, episode_id, casting.characters, location_id, material.main_episode.start, plot_text)
    if casting is not None and casting.location is not None:
        add_location(s, episode_id, casting.location, location_id)
        s.commit()

    record = s.get_one(Episode, episode_id)
    logger.info(f"{material.story.name}「{record.title}」 id={record.id} のプロットを補完した")
    return record
