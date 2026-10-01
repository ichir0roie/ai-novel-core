#!/usr/bin/env python3
"""本文を書く前に、プロットで台詞・行動のある人物を AI に挙げさせ、登場人物(`episode_character`)に足す。

作者が決めた登場人物は外さず、足すだけ。db にいない人物は人物の自動生成(`generate_character`)で作って足す。
名前だけ出る人物は AI に挙げさせず、名前の突き合わせ(`mentions.save_mentions`)に任せる。
db だけの段(`cast_material` → `plot_completer.add_cast_member`)と、AI だけの段(`cast_draft`)に分けてある。
手元では `cast_from_plot` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import age_at
from data_access_logic.character.models import CastCandidateSerialized
from data_access_logic.character.parameters import parameters_at
from data_access_logic.episode.mentions import cast_characters, mentioned_characters
from data_access_logic.episode.models import (
    EpisodeCastDraft, EpisodeCastMaterial, EpisodeCastMaterialSerialized, EpisodeCharacterCandidateDraft, StoryMaterial,
    TargetEpisode,
)
from data_access_logic.episode.plot_completer import add_cast_member, add_characters
from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import Character, CharacterRelation, ConfirmStatus, Episode, EpisodeCharacter
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの設定を整える作家です。
書く話のプロットと、決まっている登場人物・候補の人物を日本語の見出しを付けた JSON で渡すので、プロットで台詞や行動のある人物を洗い出してください。
- 名前や話題・回想に出るだけの人物、群衆、名前の要らない通りすがりは挙げません。
- 決まっている登場人物も、プロットで台詞や行動があれば挙げて、その人物idを入れてください。
- 候補の人物と同じ人物なら、その人物idを入れてください。呼び名が違っても(役職・続柄・あだ名など)、プロットの文脈と人物像から同じ人物と分かれば同じ人物です。
- 決まっている登場人物にも候補の人物にもいなければ、人物idは null にし、人物像とこの話での役どころを、作品・場所・時刻に馴染むように書いてください。"""


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
    return episode


def _candidate(character: Character, time: Stamp) -> CastCandidateSerialized:
    return CastCandidateSerialized(character=character, age=age_at(character, time), parameters=parameters_at(character, time))


def _related_ids(s: Session, cast_ids: set[int], time: Stamp) -> list[int]:
    relations = s.scalars(
        select(CharacterRelation)
        .where(or_(CharacterRelation.character_1_id.in_(cast_ids), CharacterRelation.character_2_id.in_(cast_ids)),
               alive_at(CharacterRelation, time))
        .order_by(CharacterRelation.id)
    ).all()
    return [character_id for relation in relations
            for character_id in (relation.character_1_id, relation.character_2_id)]


def _resident_ids(s: Session, location_id: int | None, time: Stamp) -> list[int]:
    if location_id is None:
        return []
    location_ids = common_query.descendant_location_ids(s, location_id)
    return list(s.scalars(common_query.resident_character_ids_select(location_ids, time)).all())


def candidate_characters(
    s: Session, episode: Episode, excluded_ids: set[int], location_id: int | None, time: Stamp,
) -> list[Character]:
    """プロット・本文に名前が出る人物・登場人物と関係のある人物・話の場所(とその中)にいる、承認済みの人物。

    `episode` は `episode_characters` と `EpisodeCharacter.character` を読んだもの。"""
    cast_ids = {character.id for character in cast_characters(episode)}
    candidate_ids = [
        *(character.id for character in mentioned_characters(s, episode, cast_ids)),
        *_related_ids(s, cast_ids, time),
        *_resident_ids(s, location_id, time),
    ]
    return list(s.scalars(
        select(Character)
        .where(Character.id.in_([character_id for character_id in candidate_ids if character_id not in excluded_ids]),
               Character.confirmed == ConfirmStatus.APPROVED)
        .order_by(Character.id)
    ).all())


def cast_material(s: Session, episode_id: int) -> EpisodeCastMaterialSerialized:
    episode = _episode(s, episode_id)
    main_episode = TargetEpisode.model_validate(episode)
    time = main_episode.start
    location_id = episode.location_id or episode.story.location_id
    cast = cast_characters(episode)
    candidates = candidate_characters(s, episode, {character.id for character in cast}, location_id, time)
    return EpisodeCastMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=main_episode,
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        cast=[_candidate(character, time) for character in cast],
        candidates=[_candidate(character, time) for character in candidates],
    )


def cast_draft(ai: AIClient, material: EpisodeCastMaterial, model: str, effort: str) -> EpisodeCastDraft | None:
    prompt = "\n".join([
        EpisodeCastMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "このプロットで台詞や行動のある人物を洗い出してください。",
    ])
    draft = ai.generate(prompt, EpisodeCastDraft, system=_SYSTEM_PROMPT,
                        timeout=constants.EPISODE_CASTING_TIMEOUT, model=model, effort=effort)
    if draft is None:
        logger.warning("プロットの人物が得られなかったので、登場人物はそのままにする")
    return draft


def split_members(
    material: EpisodeCastMaterial, draft: EpisodeCastDraft,
) -> tuple[list[int], list[EpisodeCharacterCandidateDraft]]:
    """挙がった人物を、登場人物に足す候補の人物の id と、作って足す人物に分ける。決まっている登場人物はそのまま。"""
    cast_ids = {member.character.id for member in material.cast}
    candidate_ids = {member.character.id for member in material.candidates}
    found: list[int] = []
    created: list[EpisodeCharacterCandidateDraft] = []
    for member in draft.characters:
        if member.character_id is None:
            created.append(EpisodeCharacterCandidateDraft(called=member.called, text=member.text))
        elif member.character_id in candidate_ids:
            found.append(member.character_id)
        elif member.character_id not in cast_ids:
            # 渡していない id は取り違えなので、人物を作り直さずに捨てる
            logger.warning(f"「{member.called}」の人物id={member.character_id} は候補に無いので足さない")
    return list(dict.fromkeys(found)), created


def cast_from_plot(s: Session, ai: AIClient, episode_id: int, model: str, effort: str) -> None:
    material = cast_material(s, episode_id)
    draft = cast_draft(ai, material, model, effort)
    if draft is None:
        return
    found, created = split_members(material, draft)
    for character_id in found:
        add_cast_member(s, episode_id, character_id)
    s.commit()
    location_id = material.locations[-1].id if material.locations else None
    add_characters(s, ai, episode_id, created, location_id, material.main_episode.start, material.main_episode.plot_text)
