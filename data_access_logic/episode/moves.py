#!/usr/bin/env python3
"""話の本文を確定したあと、本文の中で住まい・拠点が変わった登場人物の移動先を AI に返させる(`character/moves.py`)。

db だけの段(`moves_material`)と AI だけの段(`moves_draft`)に分けてあり、流れ(`flows/commit.py`)がつないで、
居場所は `character.steps.move_characters` で移す。
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.character.moves import move_destinations
from data_access_logic.character.record import CharacterMove
from data_access_logic.episode.material import episode_location_id, load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの設定を整える編集者です。
話の本文と、登場人物の今の居場所、移動先の候補を日本語の見出しを付けた JSON で渡すので、
この話の中で住まい・拠点が変わった登場人物(旅立ち・移住・避難・帰還・奉公に出るなど)ごとに、移動先を移動先の候補から選んでください。
- 一時の外出や、話の舞台へ出かけてきただけの人物は入れない。本文の終わりの時点で、住まい・拠点が前と変わった人物だけを入れる。
- 移動先は移動先の候補の場所idからだけ選ぶ。候補に当てはまる場所が無ければ、その人物は入れない。
- 誰も変わっていなければ character_moves は空のリストにする。"""


class MovingCharacter(Material):
    id: int
    name: str | None = None
    # 話の時刻の居場所。無ければ None
    location: LocationMaterial | None = None


class EpisodeMovesMaterial(Material):
    episode_id: int
    time: Stamp
    main_text: str
    cast: list[MovingCharacter]
    destinations: list[LocationMaterial]


class EpisodeMovesMaterialSerialized(EpisodeMovesMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "話の時刻": str(self.time),
            "登場人物": [{"人物id": member.id, "名前": member.name,
                      "今の居場所": member.location.name if member.location else None} for member in self.cast],
            "移動先の候補": [{"場所id": place.id, "名前": place.name, "種別": place.kind} for place in self.destinations],
            "本文": self.main_text,
        }


class EpisodeMovesDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    character_moves: list[CharacterMove] = Field(description="この話で住まい・拠点が変わった登場人物ごとの移動先。誰も変わっていなければ空")


def moves_material(s: Session, episode_id: int) -> EpisodeMovesMaterial | None:
    """本文・時刻・登場人物・話の場所のどれかが無ければ None(移す相手も先も決まらない)。"""
    episode = load_episode(s, episode_id)
    location_id = episode_location_id(episode)
    characters = cast_characters(episode)
    if episode.start is None or not episode.main_text.strip() or not characters or location_id is None:
        return None
    destinations = move_destinations(s, location_id, episode.start)
    if not destinations:
        return None
    cast = []
    for character in characters:
        here = s.scalars(common_query.character_location_select(character.id, episode.start)).first()
        cast.append(MovingCharacter(id=character.id, name=character.name,
                                    location=None if here is None else LocationMaterial.model_validate(here.location)))
    return EpisodeMovesMaterial(episode_id=episode.id, time=episode.start, main_text=episode.main_text, cast=cast,
                                destinations=destinations)


def moves_draft(ai: AIClient, material: EpisodeMovesMaterial) -> list[CharacterMove]:
    """AI が答えなければ空(居場所は変えない)。"""
    draft = ai.generate(
        "\n".join([EpisodeMovesMaterialSerialized.model_validate(material).model_dump_json(indent=2),
                   "この話で住まい・拠点が変わった登場人物の移動先を挙げてください。"]),
        EpisodeMovesDraft, system=_SYSTEM_PROMPT)
    if draft is None:
        logger.warning(f"話 id={material.episode_id} の移動先が得られなかったので、居場所は変えない")
        return []
    return draft.character_moves
