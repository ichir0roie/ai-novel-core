#!/usr/bin/env python3
"""話の本文から、登場人物が言ったセリフを拾い直す流れ(`CommitEpisode` のあとと、後回しの段 `RefreshGeneratedContent`)。

AI の結果は話ごとに、得たその場で書き戻す。AI が答えなかった話は前の行を残し、次の後回しの段で拾い直す。
"""
from __future__ import annotations

import logging

from data_access_logic.ai_client import AIClient
from data_access_logic.caller import call
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.speeches import SpeechesForm, allowed_speeches, speeches_draft
from data_access_logic.step import RowId

logger = logging.getLogger(__name__)


def refresh(ai: AIClient, episode_ids: list[int]) -> int:
    """`episode_ids` の話のセリフを拾い直す。書いた行の数を返す。セリフの無い話は AI を回さずに行を空にする。"""
    written = 0
    for episode_id in episode_ids:
        material = call(episode_steps.speech_material, RowId(id=episode_id))
        drafts = []
        if material.has_speech:
            drafts = speeches_draft(ai, material)
            if drafts is None:
                continue
        written += call(episode_steps.save_speeches, SpeechesForm(
            episode_id=episode_id, source_hash=material.source_hash,
            speeches=allowed_speeches(drafts, [member.id for member in material.cast], material.main_text)))
    if episode_ids:
        logger.info(f"話{len(episode_ids)}件からセリフを拾い直し、{written}件を書いた")
    return written


def refresh_stale(ai: AIClient) -> int:
    """本文が変わった話(推敲・GUI での直し・まだ拾っていない話)のセリフを拾い直す。"""
    return refresh(ai, call(episode_steps.stale_speech_episodes))
