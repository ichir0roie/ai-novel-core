#!/usr/bin/env python3
"""キー情報補完。本文は書かない(`writer.write_episode` で別に書く)。"""
from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.instructions.naming import PLACE_NAMING_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.generator import generate_character
from data_access_logic.episode.models import (
    EpisodeCastingDraft, EpisodeCastingRequestSerialized, EpisodeCharacterCandidateDraft,
    EpisodeKeyDraft, EpisodeKeyRequestSerialized, EpisodeLocationCandidateDraft, EpisodeMaterialSerialized,
)
from data_access_logic.episode.writer import episode_material
from db.schema import ConfirmStatus, Episode, EpisodeCharacter, Location
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_KEY_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルを書く作家です。
作品・前の話・書く話(時刻・場所・視点・登場人物・種)などを日本語の見出しを付けた JSON で渡すので、この話の種を書き直してください。
書き直した種は今の種とそっくり置き換わり、本文はそれだけを種にして書きます。今の種にある出来事・人物・場面・狙いは、一つも落とさずに書き直した種へ含めてください。
種は、本文全体を話の始まりから終わりまで場面の順に割り、「## 場面」(番号付きの箇条書き。一行は「場所 / 出る人 / そこで変わること」。その下に、そこで誰が何をするかを短く添える)と「## 狙い」(この話で読者に伝えたいこと・変わること)の二つの節で書いてください。
今の種に無い出来事は足さないでください。
「作者の注文」が null でなければ、今の種に加えて作者が新しい種に望むこと(展開・焦点・雰囲気など)です。今の種と合わせて取り入れてください。注文が求める出来事は足してかまいません。
場面に要るなら、登場人物にいない人物や、書く話の場所より細かい舞台(店・屋敷・部屋など)を出してかまいません。その人物・舞台には呼び名を付けてください。
直前の話は本文で、それより前の話は概要で渡します。筋をそのまま受け継いでください。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。なぞり直さず、その後の人物として書いてください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りして書かないでください。
{EVENT_AGE_INSTRUCTION}
{IDEA_CONTEXT_INSTRUCTION}"""

_CASTING_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルの設定を整える作家です。
話の材料と、その話の新しい種を日本語の見出しを付けた JSON で渡すので、新しい種に出てくるのに材料に無い人物・舞台を挙げてください。
characters には、新しい種で台詞や行動のある人物のうち、登場人物にいない人物を挙げてください。群衆や、名前の要らない通りすがりは挙げません。
人物の説明は、材料の作品・場所・時刻に馴染むように書いてください。
location には、新しい種の主な舞台が書く話の場所より細かい場所で、「この場所の中の既知の場所」にも無いときだけ、その舞台を書いてください。
location の名前は次の基準で名づけます。
{PLACE_NAMING_INSTRUCTION}"""


def _new_key(ai: AIClient, request: EpisodeKeyRequestSerialized, model: str, effort: str) -> str:
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "この話の種を書き直してください。"]),
        EpisodeKeyDraft, system=_KEY_SYSTEM_PROMPT, timeout=constants.EPISODE_KEY_TIMEOUT,
        model=model, effort=effort)
    if draft is None:
        raise ValueError("書き直した種が得られなかった")
    return draft.key


def _casting(
    s: Session, ai: AIClient, material: EpisodeMaterialSerialized, key: str, location_id: int | None,
    model: str, effort: str,
) -> EpisodeCastingDraft | None:
    known_locations = (s.scalars(select(Location).where(Location.parent_id == location_id)).all()
                       if location_id is not None else [])
    request = EpisodeCastingRequestSerialized(material=material, key=key, known_locations=known_locations)
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "新しい種に出てくるのに材料に無い人物・舞台を挙げてください。"]),
        EpisodeCastingDraft, system=_CASTING_SYSTEM_PROMPT, timeout=constants.EPISODE_CASTING_TIMEOUT,
        model=model, effort=effort)
    if draft is None:
        logger.warning("人物・舞台の候補が得られなかったので、種の書き直しだけにする")
    return draft


def _add_characters(
    s: Session, ai: AIClient, episode_id: int, candidates: list[EpisodeCharacterCandidateDraft],
    location_id: int | None, time: Stamp,
) -> None:
    rng = random.Random()
    for candidate in candidates:
        # generate_character は一人ごとに commit するので、途中で止まっても作った人物は残る
        record = generate_character(
            s, ai, rng, location_id, time, True, CharacterForm(name=candidate.called, text=candidate.text))
        if record is None:
            logger.warning(f"「{candidate.called}」の人物が得られなかったので足さない")
            continue
        # 未確認の人物は話に出せない(`CharacterMaterial`)。この話の本文に書く人物なので承認して足す
        record.confirmed = ConfirmStatus.APPROVED
        s.add(EpisodeCharacter(episode_id=episode_id, character_id=record.id))
        s.commit()
        logger.info(f"「{candidate.called}」を {record.name}(id={record.id})として登場人物に足した")


def _add_location(s: Session, episode_id: int, candidate: EpisodeLocationCandidateDraft, parent_id: int | None) -> None:
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
    s.commit()
    logger.info(f"舞台 {location.name}(id={location.id})を足し、話の場所にした")


def complete_key(
    s: Session, ai: AIClient, episode_id: int, order: str | None, model: str, effort: str,
) -> Episode:
    """今の種を核に、`order`(作者の注文。無ければ None)も取り入れて、本文全体を場面に割った種を書き直させ、
    それで種をそっくり置き換える(今の種の中身は書き直した種に含めさせる)。
    書き直した種に出るのに材料に無い人物は作って登場人物に足し、話の場所より細かい舞台はその場所の下に作って話の場所にする。
    `model` / `effort` は種の書き直しと候補の呼び出しに渡す(人物を作る呼び出しは人物の生成の既定のまま)。"""
    material = episode_material(s, ai, episode_id)
    key = _new_key(ai, EpisodeKeyRequestSerialized(material=material, order=order), model, effort)
    s.get_one(Episode, episode_id).key = key
    s.commit()

    location_id = material.locations[-1].id if material.locations else None
    casting = _casting(s, ai, material, key, location_id, model, effort)
    if casting is not None and casting.characters:
        _add_characters(s, ai, episode_id, casting.characters, location_id, material.main_episode.start)
    if casting is not None and casting.location is not None:
        _add_location(s, episode_id, casting.location, location_id)

    record = s.get_one(Episode, episode_id)
    logger.info(f"{material.story.name}「{record.title}」 id={record.id} のキー情報を補完した")
    return record
