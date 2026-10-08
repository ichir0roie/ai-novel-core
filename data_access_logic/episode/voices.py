#!/usr/bin/env python3
"""直前の五話(文体の見本)のセリフから、登場人物の話し方(一人称・二人称・三人称・口調・方言)を全体として調整する。

本文の材料を読む前に流れ(`data_access_logic/flows/episode.py` の `refresh_voices`)が回す。
調整した値は、話の時刻から効く `character_parameter` の行として書く(それより前の話には効かない)。
同じ時刻の行が既にあれば、その行を直す(同じ話の材料を読み直しても行が増えない)。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.character.parameters import parameters_at
from data_access_logic.episode.material import load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.episode.summary import recent_episodes
from data_access_logic.material import Material
from db.schema import CharacterParameter
from db.stamp import Stamp

VOICE_FIELDS = ("first_person", "second_person", "third_person", "tone", "dialect")

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者です。
直前の五話の本文と、登場人物それぞれの今の話し方を日本語の見出しを付けた JSON で渡します。
本文のセリフ(と地の文での呼び方)を根拠に、人物ごとの話し方を全体として調整した値を返してください。
- 本文にセリフのある人物だけを返す。セリフの無い人物は返さない。
- 今の値が本文のセリフと合っていれば同じ値のまま返し、合わない点は直し、本文に繰り返し表れている癖で足りないものは足す。今の値にあって本文に表れていない記述は、本文と食い違わない限り残す。
- 口調は、足し書きを重ねず、全体を一つのまとまった説明に書き直す。語尾・文の長さ・言い淀みや間・相手や場面による変わり方のような、話し方の癖だけを書く。本文の出来事・筋は書かない。
- 一人称・二人称・三人称は、本文で実際に使われている呼び方にする。相手で変わるなら、今の値の書き方に合わせる。方言は、方言の種類か標準語で話すならその癖。
- 憶測で足さない。本文に根拠のない特徴を作らない。"""


class VoiceCharacter(Material):
    id: int
    name: str | None = None
    first_person: str | None = None
    second_person: str | None = None
    third_person: str | None = None
    tone: str | None = None
    dialect: str | None = None


class VoiceSource(Material):
    episode_id: int
    # 文体の見本(同じ作品の直前の五話)。古い順
    samples: list[str]
    # 話の登場人物の、話の時刻の話し方
    characters: list[VoiceCharacter]


class VoiceSourceSerialized(VoiceSource):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "直前の話の本文(古い順)": self.samples,
            "登場人物の今の話し方": [
                {"人物id": character.id, "名前": character.name, "一人称": character.first_person,
                 "二人称": character.second_person, "三人称": character.third_person, "口調": character.tone,
                 "方言": character.dialect}
                for character in self.characters],
        }


class VoiceDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="人物id")
    first_person: str | None = Field(description="一人称。変えないなら今の値のまま")
    second_person: str | None = Field(description="二人称。変えないなら今の値のまま")
    third_person: str | None = Field(description="三人称。変えないなら今の値のまま")
    tone: str | None = Field(description="口調。全体を書き直した説明")
    dialect: str | None = Field(description="方言。変えないなら今の値のまま")


class VoiceDrafts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voices: list[VoiceDraft]


class VoiceForm(BaseModel):
    episode_id: int
    voices: list[VoiceDraft]


def voice_draft(ai: AIClient, source: VoiceSource) -> VoiceDrafts | None:
    prompt = "\n".join([
        VoiceSourceSerialized.model_validate(source).model_dump_json(indent=2),
        "直前の話のセリフから、登場人物の話し方を調整してください。",
    ])
    return ai.generate(prompt, VoiceDrafts, system=_SYSTEM_PROMPT)


def voice_source(s: Session, episode_id: int) -> VoiceSource | None:
    """見本の話か登場人物が無い(話し方を調整できない)ときは None。時刻が空でも、登場人物の今の値は始まりの値で読む。"""
    episode = load_episode(s, episode_id)
    samples = [recent.main_text for recent in recent_episodes(s, episode)]
    characters = [
        VoiceCharacter(id=character.id, name=character.name,
                       **{name: getattr(parameters_at(character, episode.start), name) for name in VOICE_FIELDS})
        for character in cast_characters(episode)]
    if not samples or not characters:
        return None
    return VoiceSource(episode_id=episode_id, samples=samples, characters=characters)


def write_voices(s: Session, episode_id: int, voices: list[VoiceDraft]) -> list[int]:
    """今の値と違う欄だけを、話の時刻から効く行へ書く。書いた人物の id を返す。
    登場人物でない人物・変わらない人物は書かない。話の時刻が空なら書かない。"""
    episode = load_episode(s, episode_id)
    start: Stamp | None = episode.start
    if start is None:
        return []
    cast = {character.id: character for character in cast_characters(episode)}
    written = []
    for voice in voices:
        character = cast.get(voice.character_id)
        if character is None:
            continue
        current = parameters_at(character, start)
        changes = {name: value.strip() for name in VOICE_FIELDS
                   if (value := getattr(voice, name)) and value.strip() and value.strip() != getattr(current, name)}
        if not changes:
            continue
        row = next((row for row in character.parameters if row.start == start), None)
        if row is None:
            row = CharacterParameter(start=start)
            character.parameters.append(row)
        for name, value in changes.items():
            setattr(row, name, value)
        written.append(character.id)
    s.flush()
    return written
