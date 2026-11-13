#!/usr/bin/env python3
"""話の登場人物の話し方の調整と、Claude が自分で書くための材料の読み出しと、本文から差分を入れる流れ。

db の段は `data_access_logic/episode/steps.py`。
話のプロットを AI の流れに書かせる段は置かない(プロットを直すのは作者と、作者の書き手で書くこのセッションの Claude)。
"""
from __future__ import annotations

import logging

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.episode import outcomes, voices
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.models import EpisodeBriefSerialized
from data_access_logic.episode.outcomes import AppliedOutcomes
from data_access_logic.flows import speech
from data_access_logic.episode_session.store import SessionStore
from data_access_logic.idea.search import keywords_of
from data_access_logic.step import RowId
from db.writer import generated
from data_access_logic.caller import call

logger = logging.getLogger(__name__)


@generated()
def refresh_voices(episode_id: int, ai: AIClient = ai_client) -> list[voices.VoiceDraft]:
    """`RefreshVoices` に当たる。同じ作品の直前の五話のセリフから、登場人物の話し方を調整して書き戻す。
    書いた人物の調整案を返す。"""
    adjusted = []
    for source in call(episode_steps.voice_sources, RowId(id=episode_id)):
        drafts = voices.voice_draft(ai, source)
        if drafts is None:
            logger.warning(f"話 id={episode_id} の登場人物の話し方を調整できなかった(AI が答えなかった)")
            continue
        # 元に入れなかった人物(根拠の見本が無い人物)を AI が返しても書かない
        asked = {character.id for character in source.characters}
        proposed = [draft for draft in drafts.voices if draft.character_id in asked]
        written = call(episode_steps.write_voices, voices.VoiceForm(episode_id=episode_id, voices=proposed))
        if written:
            logger.info(f"話 id={episode_id} の直前の話から、人物 id={written} の話し方を調整した")
        adjusted += [draft for draft in proposed if draft.character_id in written]
    return adjusted


@generated()
def reflect_episode(episode_id: int, ai: AIClient = ai_client) -> AppliedOutcomes:
    """`ReflectEpisode` に当たる。手番を回さずに書いた話の本文から、登場人物ごとの差分を AI に一度で書かせて入れ、
    セリフを拾い直す。手番を回した話は、人物役の差分を `ApplyOutcomes` で入れる(どちらも入れ方は `apply_outcomes`)。"""
    material = call(episode_steps.reflect_material, RowId(id=episode_id))
    if material is None:
        raise ValueError(f"話 id={episode_id} は時刻・本文・登場人物のどれかが空。結んで本文を確定してから反映する")
    applied = call(episode_steps.apply_outcomes, outcomes.OutcomesForm(
        episode_id=episode_id, outcomes=outcomes.outcomes_draft(ai, material)))
    applied.speeches = speech.refresh(ai, [episode_id])
    return applied


@generated()
def read_episode_brief(episode_id: int, ai: AIClient = ai_client) -> EpisodeBriefSerialized:
    """`ReadEpisodeBrief` に当たる。前の話の概要・出来事の要約は作り直さず、そのときのまま読む。
    設定は、プロット・話のセッションの行・今の本文から AI が挙げた語で引く。語の数を AI が絞るので、元ごとに挙げさせる。
    話のセッションの行は db に無く、流れを回すこの機械の手番のファイルにある。"""
    targets = call(episode_steps.brief_targets, RowId(id=episode_id))
    session = SessionStore(episode_id).text()
    sources = [*targets.word_sources, *([session] if session.strip() else [])]
    keywords = [keyword for text in sources for keyword in keywords_of(text, ai, targets.start)]
    return EpisodeBriefSerialized.model_validate(call(episode_steps.episode_brief, episode_steps.BriefForm(
        episode_id=episode_id, keywords=keywords)))
