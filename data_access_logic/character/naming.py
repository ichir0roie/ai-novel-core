#!/usr/bin/env python3
"""人物・人物以外の対象に名前を付ける。

AI だけに一つ決めさせると、同じ参考文化から毎回ありがちな名(ジャコモ・グイドなど)に寄り、別の人物でも同じ名に収束する。
そこで、環境(居場所の参考地域・文化・時代と、その人物の中身)から名前の候補を AI に `NAME_CANDIDATE_COUNT` 個出させ、
同じ場所にいる人物・対象と同じ名を除いてから、サイコロで一つ選ぶ。
"""
from __future__ import annotations

import logging
import random

from pydantic import BaseModel, ConfigDict, Field

from ai.instructions.naming import CHARACTER_NAMING_INSTRUCTION, IDEA_NAMING_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator_models import CharacterNameMaterialSerialized, NameDraft, PersonNameDraft

logger = logging.getLogger(__name__)

_CANDIDATE_INSTRUCTION = (
    f"名前の候補を {constants.NAME_CANDIDATE_COUNT} 個出してください。候補どうしは頭の音・拍数・響きを散らし、"
    "同じ名の言い換えや綴りの違いだけの候補を並べない。どれを選ばれてもこの人物に似合う名にする。"
    "渡される「同じ場所にいる人物・対象の名」とは同じ名にしない。"
    "ただし作者が付けたい名を渡したときは、それが似合うなら(同じ場所の名と重なっても)一つ目にその名を置き、合わなければ一つ目を近い響きにする。"
)

_PERSON_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
内容が決まっている人物1件に、名前と名字の候補を付けます。材料は日本語の見出しを付けた JSON で渡します。
{CHARACTER_NAMING_INSTRUCTION}
人物説明・年齢・性別・性格・体格や口調から連想できる、この人物に似合う名前にしてください。年齢からは生まれた頃の名づけの流行を、身分や家業からは名の格を考える。
居場所の参考地域・参考文化・参考時代を名の響きや漢字・カタカナの選び方の手がかりにして、同じ場所の人物として馴染む名にしてください(固有名詞をそのまま持ち込まない)。
名字は、生まれたときに名乗るものを、出身地・身分・家業・参考文化から決める。「決まっている名字」が null でなければ、どの候補の名字もその値にする。
{_CANDIDATE_INSTRUCTION}"""

_NON_PERSON_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
内容が決まっている人物以外の対象(国・組織・集団・物など)1件に、名前の候補を付けます。材料は日本語の見出しを付けた JSON で渡します。
{IDEA_NAMING_INSTRUCTION}
組織の名は場所名か役割名で呼べる形にする。
居場所の参考地域・参考文化・参考時代を名の響きや漢字・カタカナの選び方の手がかりにして、同じ場所のものとして馴染む名にしてください(固有名詞をそのまま持ち込まない)。
{_CANDIDATE_INSTRUCTION}"""


class PersonNameCandidates(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    candidates: list[PersonNameDraft] = Field(description=f"名前の候補。{constants.NAME_CANDIDATE_COUNT} 個")


class NameCandidates(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    candidates: list[NameDraft] = Field(description=f"名前の候補。{constants.NAME_CANDIDATE_COUNT} 個")


def named(ai: AIClient, rng: random.Random, material: CharacterNameMaterialSerialized,
          person: bool) -> PersonNameDraft | NameDraft | None:
    """候補が得られなければ None。作者が付けたい名を渡したときは、サイコロを振らず一つ目の候補(その名か近い響き)にする。"""
    drafts = ai.generate(
        "\n".join([material.model_dump_json(indent=2), "この一件の名前の候補を出してください。"]),
        PersonNameCandidates if person else NameCandidates,
        system=_PERSON_SYSTEM_PROMPT if person else _NON_PERSON_SYSTEM_PROMPT)
    if drafts is None or not drafts.candidates:
        return None
    unique = list({draft.name: draft for draft in drafts.candidates}.values())
    if material.hint_name:
        # 作者が決めた名は、同じ場所の名と重なっても作者の意図を通す
        return unique[0]
    avoided = set(material.avoided_names)
    fresh = [draft for draft in unique if draft.name not in avoided]
    if not fresh:
        logger.warning(f"名前の候補がどれも同じ場所の名と重なった: {[draft.name for draft in unique]}")
        fresh = unique
    return rng.choice(fresh)
