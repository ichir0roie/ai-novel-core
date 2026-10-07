#!/usr/bin/env python3
"""話の本文を確定したあと、本文で初めて会った・知り合いだと分かった登場人物どうしに、関係(`character_relation`)を AI に挙げさせる。

db だけの段(`relations_material` / `add_relations`)と AI だけの段(`relations_draft`)に分けてあり、流れ(`flows/commit.py`)がつなぐ。
足す関係は話の時刻から始まり、話で起きたことはその年の来歴の行にする(`data_access_logic/readme.md` の「関係の芯と来歴」)。
すでに関係のある向き(誰から誰へ)には足さない。
"""
from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.character.commit_character_relation import CommitCharacterRelation
from data_access_logic.character.form import CharacterRelationCreateForm
from data_access_logic.character.record import CharacterRelationHistoryRow, CharacterRelationRecord
from data_access_logic.episode.material import load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの設定を整える編集者です。
話の本文と、登場人物、登場人物どうしのすでにある関係を日本語の見出しを付けた JSON で渡すので、
この話の本文の中で、初めて会って言葉を交わした・名乗り合った、または前から知り合いだと分かった登場人物の組ごとに、関係を挙げてください。
- 関係には向きがある(誰から見た誰か)。二人のあいだの関係は、向きごとに一つずつ挙げる(A から B と、B から A)。
- すでにある関係と同じ向きの組は挙げない。
- 同じ場にいただけで、言葉もやり取りも無い組は挙げない。
- relation は短い名前(「翼を直した灯具技師」など)、text は時期を限らない間柄、history はこの話で二人のあいだに起きたことを書く。
- 人物は登場人物の人物idからだけ選ぶ。
- 誰も挙げるものが無ければ relations は空のリストにする。"""


class RelationMember(Material):
    id: int
    name: str | None = None


class KnownRelation(Material):
    character_1_id: int
    character_2_id: int
    relation: str


class EpisodeRelationsMaterial(Material):
    episode_id: int
    time: Stamp
    main_text: str
    cast: list[RelationMember]
    # 話の時刻に続いている、登場人物どうしの関係
    relations: list[KnownRelation]


class EpisodeRelationsMaterialSerialized(EpisodeRelationsMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "話の時刻": str(self.time),
            "登場人物": [{"人物id": member.id, "名前": member.name} for member in self.cast],
            "すでにある関係": [{"誰から(人物id)": relation.character_1_id, "誰へ(人物id)": relation.character_2_id,
                         "関係": relation.relation} for relation in self.relations],
            "本文": self.main_text,
        }


class RelationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_1_id: int = Field(description="誰から(関係を持つ側)の人物id")
    character_2_id: int = Field(description="誰へ(相手)の人物id")
    relation: str = Field(min_length=1, description="誰から見た相手の、短い関係の名前")
    text: str = Field(description="時期を限らない間柄")
    history: str = Field(description="この話で二人のあいだに起きたこと")


class EpisodeRelationsDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relations: list[RelationDraft] = Field(description="この話で会った・知り合いだと分かった組の、向きごとの関係。無ければ空")


class RelationsForm(BaseModel):
    relations: list[RelationDraft]
    # 関係の始まり(話の時刻)
    time: Stamp


def relations_material(s: Session, episode_id: int) -> EpisodeRelationsMaterial | None:
    """本文・時刻が無いか、登場人物が二人に満たなければ None(足す組が無い)。"""
    episode = load_episode(s, episode_id)
    characters = cast_characters(episode)
    if episode.start is None or not episode.main_text.strip() or len(characters) < 2:
        return None
    cast_ids = {character.id for character in characters}
    relations = [
        KnownRelation.model_validate(row)
        for row in s.scalars(common_query.character_relations_at_select(cast_ids, episode.start)).all()
        if row.character_1_id in cast_ids and row.character_2_id in cast_ids
    ]
    return EpisodeRelationsMaterial(episode_id=episode.id, time=episode.start, main_text=episode.main_text,
                                    cast=[RelationMember.model_validate(character) for character in characters],
                                    relations=relations)


def relations_draft(ai: AIClient, material: EpisodeRelationsMaterial) -> list[RelationDraft]:
    """AI が答えなければ空(関係は足さない)。"""
    draft = ai.generate(
        "\n".join([EpisodeRelationsMaterialSerialized.model_validate(material).model_dump_json(indent=2),
                   "この話で会った・知り合いだと分かった登場人物の組の関係を挙げてください。"]),
        EpisodeRelationsDraft, system=_SYSTEM_PROMPT)
    if draft is None:
        logger.warning(f"話 id={material.episode_id} の関係が得られなかったので、関係は足さない")
        return []
    return draft.relations


def allowed_relations(
    drafts: list[RelationDraft], character_ids: Collection[int], relations: list[KnownRelation],
) -> list[RelationDraft]:
    """AI の返した関係のうち、登場人物どうしで、まだ関係の無い向きのものだけ(一つの向きに一つ。先のものを使う)。"""
    taken = {(relation.character_1_id, relation.character_2_id) for relation in relations}
    allowed: list[RelationDraft] = []
    for draft in drafts:
        pair = (draft.character_1_id, draft.character_2_id)
        if draft.character_1_id == draft.character_2_id or pair in taken:
            continue
        if draft.character_1_id in character_ids and draft.character_2_id in character_ids:
            taken.add(pair)
            allowed.append(draft)
    return allowed


def add_relations(s: Session, form: RelationsForm) -> list[CharacterRelationRecord]:
    return [
        CommitCharacterRelation(CharacterRelationCreateForm(
            character_1_id=draft.character_1_id, character_2_id=draft.character_2_id, relation=draft.relation,
            text=draft.text, start=form.time,
            histories=[CharacterRelationHistoryRow(start=form.time, description=draft.history)],
        )).execute(s)
        for draft in form.relations
    ]
