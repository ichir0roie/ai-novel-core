#!/usr/bin/env python3
"""話の本文の「」のセリフを、言った登場人物ごとに拾い、原文・鮮明・あやふやの三つの覚えにして `character_speech` に書く。

人物役は、前の話で自分が言ったセリフを、言ってからの日数で原文・鮮明・あやふやのどれかで読む(`character/knowledge.py`)。
db だけの段(`speech_material` / `save_speeches` / `stale_speech_episodes`)と AI だけの段(`speeches_draft`)に分けてあり、
流れ(`flows/speech.py`)がつなぐ。本文を確定した `CommitEpisode` のあとと、後回しの段(`RefreshGeneratedContent`)で回す。
後回しの段は、本文が変わった話(行の `source_hash` が本文と食い違う・セリフがあるのに行が無い)だけを拾い直す。
"""
from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from data_access_logic.ai_client import AIClient
from data_access_logic.episode.material import load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.material import Material
from db.schema import CharacterSpeech, Episode, StyleScope, summary_source_hash

logger = logging.getLogger(__name__)

_SYSTEM = """\
話の本文と登場人物を渡すので、本文の「」で括られたセリフを、本文に出る順に一つずつ挙げ、言った人物と、三つの覚えを返す。
- 一つの「」を一つのセリフとして挙げる。同じ人物のひと続きの言葉でも、地の文で切られていれば別々に挙げる。
- 言った人物は登場人物の人物idからだけ選ぶ。登場人物にいない人物(端役・群衆)のセリフと、言った人物の分からないセリフは挙げない。
- 声に出していない文(手紙・書きつけ・看板・心の声)は挙げない。
- 鮮明とあやふやは、言った本人が後で思い出す形にし、本人の口調で書く。「」は付けない。"""

# セリフの無い本文には AI を回さない
_QUOTE = "「"


class SpeechMember(Material):
    id: int
    name: str | None = None


class EpisodeSpeechMaterial(Material):
    episode_id: int
    main_text: str
    cast: list[SpeechMember]

    @property
    def source_hash(self) -> str:
        return summary_source_hash(self.main_text)

    @property
    def has_speech(self) -> bool:
        return bool(self.cast) and _QUOTE in self.main_text


class EpisodeSpeechMaterialSerialized(EpisodeSpeechMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {"登場人物": [{"人物id": member.id, "名前": member.name} for member in self.cast],
                "本文": self.main_text}


class SpeechDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="言った人物の人物id")
    verbatim: str = Field(min_length=1, description="「」の中の文を、一字も変えずにそのまま。「」は付けない")
    vivid: str = Field(min_length=1, description="一年ほど後に本人が思い出すセリフ。言い回しは少し崩れてよいが、中身と要の語は残す")
    vague: str = Field(min_length=1, description="何年も後に本人がおぼろげに思い出す形。誰に何を言ったかの大筋だけを短く")


class EpisodeSpeechDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speeches: list[SpeechDraft] = Field(description="登場人物のセリフを本文に出る順に。無ければ空")


class SpeechesForm(BaseModel):
    episode_id: int
    # 拾った本文の sha256
    source_hash: str
    speeches: list[SpeechDraft]


def speech_material(s: Session, episode_id: int) -> EpisodeSpeechMaterial:
    episode = load_episode(s, episode_id)
    return EpisodeSpeechMaterial(episode_id=episode.id, main_text=episode.main_text,
                                 cast=[SpeechMember.model_validate(character) for character in cast_characters(episode)])


def speeches_draft(ai: AIClient, material: EpisodeSpeechMaterial) -> list[SpeechDraft] | None:
    """AI が答えなければ None(前の行を残し、次の後回しの段で拾い直す)。"""
    draft = ai.generate(
        "\n".join([EpisodeSpeechMaterialSerialized.model_validate(material).model_dump_json(indent=2),
                   "本文の登場人物のセリフを、出る順に挙げる。"]),
        EpisodeSpeechDraft, system=_SYSTEM, style_scope=StyleScope.ACTING)
    if draft is None:
        logger.warning(f"話 id={material.episode_id} のセリフが得られなかった。次の後回しの段で拾い直す")
        return None
    return draft.speeches


def allowed_speeches(drafts: list[SpeechDraft], character_ids: Collection[int], main_text: str) -> list[SpeechDraft]:
    """登場人物が言った、本文にそのまま出るセリフだけ(AI が言い換えた原文は覚えにならない)。"""
    allowed = [draft for draft in drafts if draft.character_id in character_ids and draft.verbatim in main_text]
    if len(allowed) < len(drafts):
        logger.info(f"拾ったセリフ{len(drafts)}件のうち、登場人物でない・本文に無い{len(drafts) - len(allowed)}件を外した")
    return allowed


def save_speeches(s: Session, form: SpeechesForm) -> int:
    """話の行をまとめて置き換える。書いた行の数を返す。"""
    s.execute(delete(CharacterSpeech).where(CharacterSpeech.episode_id == form.episode_id))
    s.add_all(CharacterSpeech(episode_id=form.episode_id, character_id=draft.character_id, position=position,
                              verbatim=draft.verbatim, vivid=draft.vivid, vague=draft.vague,
                              source_hash=form.source_hash)
              for position, draft in enumerate(form.speeches))
    return len(form.speeches)


def stale_speech_episodes(s: Session) -> list[int]:
    """行を拾い直す話。行の本文が今の本文と食い違うか、登場人物とセリフがあるのに行が無い話。"""
    hashes: dict[int, set[str]] = {}
    for episode_id, source_hash in s.execute(select(CharacterSpeech.episode_id, CharacterSpeech.source_hash)).all():
        hashes.setdefault(episode_id, set()).add(source_hash)
    episodes = s.scalars(
        select(Episode).options(selectinload(Episode.episode_characters))
        .order_by(Episode.start.asc().nulls_last(), Episode.id)
        .execution_options(populate_existing=True)).all()
    stale: list[int] = []
    for episode in episodes:
        written = hashes.get(episode.id)
        if written is not None:
            if written != {summary_source_hash(episode.main_text)}:
                stale.append(episode.id)
        elif _QUOTE in episode.main_text and any(not link.mentioned for link in episode.episode_characters):
            stale.append(episode.id)
    return stale

