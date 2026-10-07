#!/usr/bin/env python3
"""人物・人物以外の対象に名前を付ける。

AI だけに一つ決めさせると、同じ参考文化から毎回ありがちな名(ジャコモ・グイドなど)に寄り、別の人物でも同じ名に収束する。
そこで、環境(居場所の参考地域・文化・時代と、その人物の中身)から名前の候補を AI に `NAME_CANDIDATE_COUNT` 個出させ、
避ける名を除いてから、サイコロで一つ選ぶ。

候補を出させても、材料が似ていれば AI は毎回同じ候補を並べる。人物では、名の頭の音(行)と拍数を先にサイコロで決めて
縛りとして渡し、AI のありがちな名から外す。

候補は次の順で絞る。絞って何も残らなければ、その段は飛ばす(前の段ほど優先する)。
1. 同じ場所にいる人物・対象と同じ名を除く
2. 同じ場所にいる人物・対象と頭の二音が同じ名(「ゼノ」と「ゼノス」)を除く。読みの分からない漢字の名とは比べない
3. 世界のどこかで使われている名を除く
4. サイコロで決めた頭の音・拍数に合わない名を除く(AI が縛りを守らなかったとき)
"""
from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ai.instructions.naming import CHARACTER_NAMING_INSTRUCTION, IDEA_NAMING_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator_models import CharacterNameMaterialSerialized, NameDraft, PersonNameDraft

logger = logging.getLogger(__name__)

# 名の頭の音として引く行。ぱ行・わ行は名の頭に来ることが少なく、どの文化でも似合う名が出にくいので引かない
_HEAD_ROWS = {
    "あ行": "あいうえお", "か行": "かきくけこ", "さ行": "さしすせそ", "た行": "たちつてと", "な行": "なにぬねの",
    "は行": "はひふへほ", "ま行": "まみむめも", "や行": "やゆよ", "ら行": "らりるれろ",
    "が行": "がぎぐげご", "ざ行": "ざじずぜぞ", "だ行": "だぢづでど", "ば行": "ばびぶべぼゔ",
}
# 前の音と合わせて一拍になる小書きの仮名(「きゃ」「ふぁ」)。「っ」「ー」「ん」は一拍に数える
_SMALL_KANA = set("ゃゅょぁぃぅぇぉゎ")
# 長音「ー」を前の音の母音に読み替える(「トーマ」と「とうま」を同じ響きとして比べる)。お段・え段の長音は
# 名の読みでは「う」「い」と書くことが多いのでそれに合わせる
_LONG_VOWELS = {
    **dict.fromkeys("あかさたなはまやらわがざだばぱぁゃゎ", "あ"), **dict.fromkeys("いきしちにひみりぎじぢびぴぃ", "い"),
    **dict.fromkeys("うくすつぬふむゆるぐずづぶぷゔぅゅ", "う"), **dict.fromkeys("えけせてねへめれげぜでべぺぇ", "い"),
    **dict.fromkeys("おこそとのほもよろをごぞどぼぽぉょ", "う"),
}

_CANDIDATE_INSTRUCTION = (
    f"名前の候補を {constants.NAME_CANDIDATE_COUNT} 個出してください。候補どうしは響きを散らし、"
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
「名の音の縛り」が null でなければ、どの候補の名(名字を含めない)もその頭の音・拍数にする。その音で始まる名がこの文化に無理なく無ければ、近い音でよい。
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


class NameSound(BaseModel):
    """サイコロで決めた、名の頭の音(行)と拍数。"""

    row: str
    moras: int

    def fits(self, reading: str) -> bool:
        return bool(reading) and reading[0] in _HEAD_ROWS[self.row] and _mora_count(reading) == self.moras

    def __str__(self) -> str:
        return f"{self.row}で始まる{self.moras}拍"


def drawn_sound(rng: random.Random) -> NameSound:
    return NameSound(row=rng.choice(sorted(_HEAD_ROWS)), moras=rng.randint(*constants.NAME_MORA_RANGE))


def _mora_count(reading: str) -> int:
    return sum(1 for char in reading if char not in _SMALL_KANA)


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
    """候補が得られなければ None。作者が付けたい名を渡したときは、サイコロを振らず一つ目の候補(その名か近い響き)にする。"""
    sound = drawn_sound(rng) if person and not material.hint_name else None
    drafts = ai.generate(
        "\n".join([material.model_dump_json(indent=2),
                   *([f"名の音の縛り: {sound or 'null'}"] if person else []),
                   "この一件の名前の候補を出してください。"]),
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
    avoided_heads = {head for name in avoided if (reading := _kana(name)) and (head := _head(reading))}
    fresh = _narrowed(fresh, lambda draft: not _resembles(_reading(draft), avoided_heads))
    used = set(material.used_names)
    fresh = _narrowed(fresh, lambda draft: draft.name not in used)
    if sound is not None:
        fresh = _narrowed(fresh, lambda draft: (reading := _reading(draft)) is not None and sound.fits(reading))
    return rng.choice(fresh)
