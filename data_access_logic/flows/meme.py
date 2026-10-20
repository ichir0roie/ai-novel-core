#!/usr/bin/env python3
"""ミームの抜き出し・分類と、対の無いミームにアンチミームを足す流れ。

AI の結果は束ごとに、得たその場で書き戻す。抜き出すのは渡した行だけで、抜き出せなかった元は警告を出して飛ばす。
"""
from __future__ import annotations

import logging

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.meme import extractor
from data_access_logic.meme import steps as meme_steps
from data_access_logic.source_text import SourceRow, SourceRows, batches
from data_access_logic.caller import call

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


def _pair(ai: AIClient) -> int:
    """分類を振った後に回す(アンチミームは元のミームの分類を引き継ぐ)。"""
    unpaired = call(meme_steps.unpaired_sources)
    added = 0
    for batch in batches(unpaired, constants.MEME_BATCH_LETTERS):
        antis = extractor.anti_draft(ai, batch)
        if antis is None:
            logger.warning(f"ミーム{len(batch)}件のアンチミームを作れなかった。次の回に作り直す")
            continue
        added += call(meme_steps.save_anti_memes, meme_steps.AntiMemesForm(antis=antis))
    if unpaired:
        logger.info(f"アンチミームの無いミーム{len(unpaired)}件のうち、{added}件にアンチミームを足した")
    return added


def refresh(ai: AIClient, rows: list[SourceRow]) -> int:
    """`rows` の本文からミームを抜き出し、分類の空いたミームに分類を、対の無いミームにアンチミームを足す。
    足したミームの件数(アンチミームを含む)を返す。"""
    sources = call(meme_steps.sources, SourceRows(rows=rows)) if rows else []
    added = 0
    for batch in batches(sources, constants.MEME_BATCH_LETTERS):
        decided = extractor.extraction_draft(ai, batch)
        if decided is None:
            logger.warning(f"元{len(batch)}件からミームを抜き出せなかった")
            continue
        fresh = extractor.without_duplicates(ai, decided.memes, call(meme_steps.meme_texts))
        if fresh is None:
            logger.warning(f"元{len(batch)}件から抜き出したミームの重複を確かめられなかった")
            continue
        added += call(meme_steps.save_memes, meme_steps.MemesForm(memes=fresh))
    if sources:
        logger.info(f"元{len(sources)}件から抜き出し、ミームを{added}件足した")
    _classify(ai)
    return added + _pair(ai)
