#!/usr/bin/env python3
"""ミームの抜き出しと分類を、API 越しに回す(手元の `data_access_logic/meme/extractor.refresh` に当たる)。

AI の結果は束ごとに、得たその場で書き戻す。抜き出せなかった元は印を付けずに残し、次の回に抜き出し直す。
"""
from __future__ import annotations

import logging

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.meme import extractor
from data_access_logic.meme import steps as meme_steps
from data_access_logic.source_text import batches
from web_session.api import call

logger = logging.getLogger(__name__)


def _classify(ai: AIClient) -> int:
    unclassified = call(meme_steps.unclassified_sources)
    classified = 0
    for batch in batches(unclassified, constants.MEME_BATCH_LETTERS):
        categories = extractor.classify_draft(ai, batch)
        if categories is None:
            continue
        classified += call(meme_steps.save_categories, meme_steps.CategoriesForm(categories=categories))
    if unclassified:
        logger.info(f"分類の空いたミーム{len(unclassified)}件のうち、{classified}件に分類を振った")
    return classified


def refresh(ai: AIClient) -> int:
    """足したミームの件数を返す。"""
    pending = call(meme_steps.pending_sources)
    added = 0
    for batch in batches(pending, constants.MEME_BATCH_LETTERS):
        decided = extractor.extraction_draft(ai, batch)
        if decided is None:
            logger.warning(f"元{len(batch)}件からミームを抜き出せなかった。次の回に抜き出し直す")
            continue
        fresh = extractor.without_duplicates(ai, decided.memes, call(meme_steps.meme_texts))
        if fresh is None:
            logger.warning(f"元{len(batch)}件から抜き出したミームの重複を確かめられなかった。次の回に抜き出し直す")
            continue
        added += call(meme_steps.save_memes, meme_steps.MemesForm(memes=fresh, sources=batch))
    if pending:
        logger.info(f"元{len(pending)}件から抜き出し、ミームを{added}件足した")
    _classify(ai)
    return added
