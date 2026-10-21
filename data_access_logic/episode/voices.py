#!/usr/bin/env python3
"""同じ作品の直前の五話のセリフから、登場人物の話し方(一人称・二人称・三人称・口調・方言)を全体として調整する。

本文の材料を読む前に流れ(`data_access_logic/flows/episode.py` の `refresh_voices`)が回す。
調整した値は、話の時刻から効く `character_parameter` の行として書く(それより前の話には効かない)。
同じ時刻の行が既にあれば、その行を直す(同じ話の材料を読み直しても行が増えない)。
話し方を最後に決めた行より前に書かれた見本は、その人物の話し方の根拠にしない(作者が変えた話し方を、変える前の
セリフで戻さない)。根拠にできる見本が無い人物は調整しない。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.character.parameters import parameters_at
from data_access_logic.episode.material import load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.episode.past import recent_episodes
from data_access_logic.material import Material
from db.schema import Character, CharacterParameter, StyleScope
from db.stamp import Stamp

VOICE_FIELDS = ("first_person", "second_person", "third_person", "tone", "dialect")

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者だ。
直前の五話の本文と、登場人物それぞれの今の話し方を日本語の見出しを付けた JSON で渡す。
本文のセリフ(と地の文での呼び方)を根拠に、人物ごとの話し方を全体として調整した値を返す。
- 本文にセリフのある人物だけを返す。セリフの無い人物は返さない。
- 今の値が本文のセリフと合っていれば同じ値のまま返し、合わない点は直す。本文に繰り返し表れている語尾・呼び方・話す長さの癖で、今の値に無いものだけを足す。今の値にあって本文に表れていない語尾・呼び方は、本文と食い違わない限り残す。
- 口調は、足し書きを重ねず、全体を一つのまとまった説明に書き直す。語尾・文の長さ・言い淀みや間・相手や場面による変わり方のような、話し方の癖だけを書く。本文の出来事・筋は書かない。
- 口調は 200 字ほどに収める。超えるなら、その場かぎりの振る舞いから削り、語尾・呼び方・話す長さを残す。
- 本文のセリフを例として書き写さない。例は語尾・呼び方を示す短いもの(「〜だろ」「じいさん」)を三つまでにする。決め台詞・教訓めいた一言・格好をつけた言い回しは口調に入れない。
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
    story_id: int
    # 同じ作品の直前の五話のうち、ここの人物の話し方の根拠にできる話。古い順
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
    tone: str | None = Field(description="口調。全体を書き直した 200 字ほどの説明")
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
        "直前の話のセリフから、登場人物の話し方を調整する。",
    ])
    return ai.generate(prompt, VoiceDrafts, system=_SYSTEM_PROMPT, style_scope=StyleScope.CHARACTER,
                       story_id=source.story_id)


def voice_sources(s: Session, episode_id: int) -> list[VoiceSource]:
    """人物ごとに、話し方を最後に決めた行から後に書かれた見本だけを根拠にする。根拠の見本が同じ人物を一つの元にまとめる。
    見本・登場人物が無い話、時刻の空の話(書き戻せない)は空。"""
    episode = load_episode(s, episode_id)
    start = episode.start
    if start is None:
        return []
    samples = recent_episodes(s, episode)
    groups: dict[tuple[int, ...], list[VoiceCharacter]] = {}
    for character in cast_characters(episode):
        since = _voice_since(character, start)
        chosen = tuple(index for index, sample in enumerate(samples)
                       if since is None or (sample.start is not None and sample.start >= since))
        if not chosen:
            continue
        values = parameters_at(character, start)
        groups.setdefault(chosen, []).append(VoiceCharacter(
            id=character.id, name=character.name, **{name: getattr(values, name) for name in VOICE_FIELDS}))
    return [VoiceSource(episode_id=episode_id, story_id=episode.story_id,
                        samples=[samples[index].main_text for index in chosen], characters=characters)
            for chosen, characters in groups.items()]


def _voice_since(character: Character, time: Stamp) -> Stamp | None:
    """時刻までに話し方の欄を決めた行のうち、一番遅く始まる行の始まり。始まりのある行が無ければ None。"""
    return max((row.start for row in character.parameters
                if row.start is not None and row.start <= time and any(getattr(row, name) for name in VOICE_FIELDS)),
               default=None)


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
