#!/usr/bin/env python3
"""人物・人物以外の対象に名前を付ける。

AI だけに一つ決めさせると、同じ参考文化から毎回ありがちな名(ジャコモ・グイドなど)に寄り、別の人物でも同じ名に収束する。
そこで、環境(居場所の参考地域・文化・時代と、その人物の中身)から名前の候補を AI に `NAME_CANDIDATE_COUNT` 個出させ、
避ける名を除いてから、サイコロで一つ選ぶ。

候補を出させても、材料が似ていれば AI は毎回同じ文化のありがちな名を並べる。人物では、先に名の元にする意味の語を
ミーム・行動原理・性格から AI に挙げさせ、そこからサイコロで選んだ意味を、参考文化の言語に訳して名にさせる。
人物ごとに違うミームから意味を取るので、同じ文化の人物でも名の元の語がばらける。

候補は次の順で絞る。絞って何も残らなければ、その段は飛ばす(前の段ほど優先する)。
1. 同じ場所にいる人物・対象と同じ名を除く
2. 同じ場所にいる人物・対象と頭の二音が同じ名(「ゼノ」と「ゼノス」)を除く。読みの分からない漢字の名とは比べない
3. 世界のどこかで使われている名を除く
"""
from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator_models import CharacterNameMaterialSerialized, NameDraft, PersonNameDraft
from db.schema import StyleScope

logger = logging.getLogger(__name__)

# 長音「ー」を前の音の母音に読み替える(「トーマ」と「とうま」を同じ響きとして比べる)。お段・え段の長音は
# 名の読みでは「う」「い」と書くことが多いのでそれに合わせる
_LONG_VOWELS = {
    **dict.fromkeys("あかさたなはまやらわがざだばぱぁゃゎ", "あ"), **dict.fromkeys("いきしちにひみりぎじぢびぴぃ", "い"),
    **dict.fromkeys("うくすつぬふむゆるぐずづぶぷゔぅゅ", "う"), **dict.fromkeys("えけせてねへめれげぜでべぺぇ", "い"),
    **dict.fromkeys("おこそとのほもよろをごぞどぼぽぉょ", "う"),
}


_MEANING_SYSTEM = """\
内容が決まっている人物1件の、名と名字の元にする意味の語を挙げる。
名の元にする意味は、ミーム・行動原理からこの人物の芯を表す語を挙げる。
それとは別に、性格・人物説明から表す語を挙げる(ミームが空のときに使う)。
名字の元にする意味は、出身地・身分・家業・参考文化から挙げる。"""

_PERSON_SYSTEM = """\
内容が決まっている人物1件に、名前と名字の候補を付ける。
名づけに使う言語は、居場所の参考地域・参考文化・参考時代だけから決める(方言・口調・一人称は手がかりにしない)。
「名の意味」が null でなければ、その意味をその言語の語に訳し、その言語の名として通る形に整えてカタカナで書く。参考地域が漢字を使う地域のときだけ、意味を表す漢字で書く。
「名の意味」が null なら、人物説明・年齢・性別・性格から名を作る。
名字は、「名字の意味」が null でなければ同じ手順でその意味から作り、null なら出身地・身分・家業・参考文化から決める。「決まっている名字」が null でなければ、どの候補の名字もその値にする。
名前の候補を、渡す数だけ出す。同じ名の言い換えや綴りの違いだけの候補を並べない。
「同じ場所にいる人物・対象の名」と、同じ名・似た響きの名にしない。
作者が付けたい名を渡したときは、一つ目にその名かその近い響きを置く。"""

_THING_SYSTEM = """\
内容が決まっている人物以外の対象(国・組織・集団・物など)1件に、名前の候補を、渡す数だけ付ける。
居場所の参考地域・参考文化・参考時代を、名の響き・表記の手がかりにする(固有名詞を持ち込まない)。
同じ名の言い換えや綴りの違いだけの候補を並べない。
「同じ場所にいる人物・対象の名」と、同じ名・似た響きの名にしない。"""


class PersonNameCandidates(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    # 候補より先に書かせ、言語を参考地域・参考文化から決めてから名を作らせる
    language: str = Field(description="名づけに使う言語")
    candidates: list[PersonNameDraft] = Field(description=f"名前の候補。{constants.NAME_CANDIDATE_COUNT} 個")


class NameCandidates(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    candidates: list[NameDraft] = Field(description=f"名前の候補。{constants.NAME_CANDIDATE_COUNT} 個")


class NameMeanings(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    from_memes: list[str] = Field(
        description=f"ミーム・行動原理から取った、名の元にする意味の語。{constants.NAME_MEANING_COUNT} 個。ミームが空なら空")
    from_character: list[str] = Field(description="性格・人物説明から取った、名の元にする意味の語")
    family: list[str] = Field(description="名字の元にする意味の語。決まっている名字があれば空")


class DrawnMeanings(BaseModel):
    """サイコロで選んだ、名と名字の元にする意味。"""

    given: list[str]
    family: str | None


def drawn_meanings(ai: AIClient, rng: random.Random, material: CharacterNameMaterialSerialized) -> DrawnMeanings | None:
    """AI に意味の語を挙げさせ、名の意味を `NAME_MEANING_PICK_RANGE` 個・名字の意味を一つ選ぶ。挙がらなければ None。
    名の意味はミームから取った語を優先し、それが無いときだけ性格・人物説明から取った語を使う。"""
    meanings = ai.generate("\n".join([material.model_dump_json(indent=2),
                                      f"この人物の名と名字の元にする意味を挙げる。名の意味の数: {constants.NAME_MEANING_COUNT}"]),
                           NameMeanings, system=_MEANING_SYSTEM, style_scope=StyleScope.CHARACTER)
    if meanings is None:
        return None
    given = _words(meanings.from_memes) or _words(meanings.from_character)
    if not given:
        return None
    family = _words(meanings.family)
    return DrawnMeanings(given=rng.sample(given, min(rng.randint(*constants.NAME_MEANING_PICK_RANGE), len(given))),
                         family=rng.choice(family) if family else None)


def _words(words: list[str]) -> list[str]:
    return list(dict.fromkeys(word.strip() for word in words if word.strip()))


def _kana(text: str) -> str | None:
    """仮名だけの名をひらがなにしたもの。漢字などが混じれば読みが分からないので None。"""
    hiragana = "".join(chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char
                       for char in text if not char.isspace() and char != "・")
    return hiragana if hiragana and all("ぁ" <= char <= "ゖ" or char == "ー" for char in hiragana) else None


def _reading(draft: PersonNameDraft | NameDraft) -> str | None:
    if isinstance(draft, PersonNameDraft):
        return _kana(draft.reading)
    return _kana(draft.name)


def _head(reading: str) -> str | None:
    """頭の二音。一音しかない名は比べない。"""
    sounds = ""
    for char in reading:
        sounds += _LONG_VOWELS.get(sounds[-1:], "") if char == "ー" else char
    return sounds[:2] if len(sounds) >= 2 else None


def _resembles(reading: str | None, avoided_heads: set[str]) -> bool:
    return reading is not None and _head(reading) in avoided_heads


def _narrowed[Draft: PersonNameDraft | NameDraft](
    drafts: Sequence[Draft], keep: Callable[[Draft], bool],
) -> list[Draft]:
    return [draft for draft in drafts if keep(draft)] or list(drafts)


def named(ai: AIClient, rng: random.Random, material: CharacterNameMaterialSerialized,
          person: bool) -> PersonNameDraft | NameDraft | None:
    """候補が得られなければ None。作者が付けたい名を渡したときは、意味を選ばず一つ目の候補(その名か近い響き)にする。"""
    meanings = drawn_meanings(ai, rng, material) if person and not material.hint_name else None
    drafts = ai.generate(
        "\n".join([material.model_dump_json(indent=2),
                   *([f"名の意味: {'、'.join(meanings.given) if meanings else 'null'}",
                      f"名字の意味: {(meanings.family if meanings else None) or 'null'}"] if person else []),
                   f"この一件の名前の候補を出す。候補の数: {constants.NAME_CANDIDATE_COUNT}"]),
        PersonNameCandidates if person else NameCandidates,
        system=_PERSON_SYSTEM if person else _THING_SYSTEM, style_scope=StyleScope.CHARACTER)
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
    avoided_heads = {head for name in avoided if (reading := _kana(name)) and (head := _head(reading))}
    fresh = _narrowed(fresh, lambda draft: not _resembles(_reading(draft), avoided_heads))
    used = set(material.used_names)
    fresh = _narrowed(fresh, lambda draft: draft.name not in used)
    return rng.choice(fresh)
