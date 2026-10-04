#!/usr/bin/env python3
"""出来事の種の抜き出しと棚卸しの流れ。

AI の結果は束ごとに、得たその場で書き戻す。
"""
from __future__ import annotations

import logging

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.event_seed import extractor
from data_access_logic.event_seed import steps as seed_steps
from data_access_logic.source_text import batches
from data_access_logic.step import RowIds
from data_access_logic.caller import call

logger = logging.getLogger(__name__)


def refresh(ai: AIClient) -> int:
    """抜き出せなかった元は印を付けずに残し、次の回に抜き出し直す。足した種の件数を返す。"""
    pending = call(seed_steps.pending_sources)
    added = 0
    for batch in batches(pending, constants.EVENT_SEED_BATCH_LETTERS):
        decided = extractor.extraction_draft(ai, batch)
        if decided is None:
            logger.warning(f"元{len(batch)}件から種を抜き出せなかった。次の回に抜き出し直す")
            continue
        added += call(seed_steps.save_seeds, seed_steps.SeedsForm(seeds=decided.seeds, sources=batch))
    if pending:
        logger.info(f"元{len(pending)}件から抜き出し、種を{added}件足した")
    return added


def consolidate(ai: AIClient) -> None:
    """棚卸し前の種が `constants.EVENT_SEED_CONSOLIDATE_EVERY` 件たまったら、似た種をまとめる。"""
    piles = call(seed_steps.seed_piles)
    if piles is None:
        return
    fresh = piles.fresh
    for chunk in batches(piles.settled, constants.EVENT_SEED_CONSOLIDATE_LETTERS) or [[]]:
        merges = extractor.merges_draft(ai, fresh, chunk)
        if merges is None:
            logger.warning("棚卸しの答えが得られなかった。次の回にやり直す")
            return
        call(seed_steps.apply_merges, seed_steps.MergesForm(merges=merges))
        merged_ids = {seed_id for merge in merges for seed_id in merge.ids}
        fresh = [seed for seed in fresh if seed.id not in merged_ids]
    call(seed_steps.settle_seeds, RowIds(ids=[seed.id for seed in fresh]))


def refresh_and_consolidate(ai: AIClient) -> None:
    """出来事を足したあとに呼ぶ。種を抜き出していない元(足した出来事自身も含む)から種を足し、たまっていれば似た種をまとめる。"""
    refresh(ai)
    consolidate(ai)
