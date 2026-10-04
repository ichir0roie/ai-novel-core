#!/usr/bin/env python3
"""出来事の種は、元の本文から時代・場所・固有名詞を抜いたもの。出来事の生成(`GenerateEvent`)で候補を立てる手がかりに引く。

db だけの段(`pending_sources` / `save_seeds` / `seed_piles` / `apply_merges` / `settle_seeds` / `seed_pool`)と、
AI だけの段(`extraction_draft`、`merges_draft`)に分けてある。流れ(`data_access_logic/flows/event_seed.py`)がつなぐ。
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.event_seed.models import (
    ConsolidateDraft, ConsolidateRequestSerialized, SeedMerge, SeedPiles, SeedsDraft, StoredSeed,
)
from data_access_logic.query import event_seed_query
from data_access_logic.source_text import SourceBatchSerialized, SourceText, row_of, source_of
from db.schema import Character, Episode, Event, EventSeed

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
話の骨組み・人物の筋書き・起きた出来事を番号つきの JSON で渡すので、それぞれから、ほかの時代・ほかの場所・ほかの人物にも起こせる「出来事の種」を抜き出してください。
- 人名・地名・組織名・その作品だけの用語と、年代を抜く。人物は「古参の番兵」「商家の娘」のような立場で書く。
- 一つの種は一〜二文。誰が、何をきっかけに、何をして、どんな揺れや変化が起きるかを書く。
- 作者の前書き・使用環境・書き方の約束・構成表など、出来事にならない文からは抜き出さない。
- 一つの元から 0〜3 件。同じ元の中で似た種は一つにまとめる。"""

_CONSOLIDATE_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
出来事の種を「新しい種」と「棚卸し済みの種」に分けて番号つきで渡すので、同じ出来事を言い換えただけの種の組を見つけ、一つにまとめてください。
- 立場・きっかけ・展開・結末がほぼ同じものだけをまとめる。題材が近いだけで展開の違うものはまとめない。
- 組には新しい種を一つ以上含める。棚卸し済みの種どうしは、既に見比べてあるのでまとめない。
- まとめた種は一〜二文。まとめる種の要素を落とさず、人名・地名・年代は入れない。
- まとめる組が無ければ merges は空のリストにする。"""

def pending_sources(s: Session) -> list[SourceText]:
    """まだ種を抜き出していない元。話はプロット(`plot_text`)を、無ければ本文を使う。人物は筋書き(`plot`)だけを使う。"""
    sources: list[SourceText] = []
    for episode in s.scalars(event_seed_query.unseeded_select(Episode, Episode.plot_text, Episode.main_text)).all():
        sources.append(source_of(episode, "話の骨組み", episode.plot_text.strip() or episode.main_text))
    for character in s.scalars(event_seed_query.unseeded_select(Character, Character.plot)).all():
        sources.append(source_of(character, "人物の筋書き", character.plot or ""))
    for event in s.scalars(event_seed_query.unseeded_select(Event, Event.text)).all():
        sources.append(source_of(event, "出来事", event.text))
    return sources


def extraction_draft(ai: AIClient, batch: list[SourceText]) -> SeedsDraft | None:
    return ai.generate(
        "\n".join([SourceBatchSerialized(sources=batch).model_dump_json(indent=2),
                   "それぞれの元から出来事の種を抜き出してください。"]),
        SeedsDraft, system=_SYSTEM_PROMPT)


def save_seeds(s: Session, seeds: list[str], sources: list[SourceText]) -> int:
    """種を足し、元に抜き出し済みの印を付ける。足した件数を返す。"""
    s.add_all(EventSeed(text=seed) for seed in seeds)
    for source in sources:
        row_of(s, source.table, source.id).event_seeded = True
    s.flush()
    return len(seeds)


def seed_piles(s: Session) -> SeedPiles | None:
    """棚卸し前の種が `constants.EVENT_SEED_CONSOLIDATE_EVERY` 件たまっていなければ None。"""
    fresh = s.scalars(select(EventSeed).where(EventSeed.consolidated.is_(False)).order_by(EventSeed.id)).all()
    if len(fresh) < constants.EVENT_SEED_CONSOLIDATE_EVERY:
        return None
    settled = s.scalars(select(EventSeed).where(EventSeed.consolidated.is_(True)).order_by(EventSeed.id)).all()
    return SeedPiles(fresh=[StoredSeed.model_validate(seed) for seed in fresh],
                     settled=[StoredSeed.model_validate(seed) for seed in settled])


def merges_draft(ai: AIClient, fresh: list[StoredSeed], settled: list[StoredSeed]) -> list[SeedMerge] | None:
    """新しい種を一つ以上含む組だけをまとめる。答えが得られなければ None。"""
    numbered = [*fresh, *settled]
    request = ConsolidateRequestSerialized(fresh=fresh, settled=settled)
    decided = ai.generate(
        "\n".join([request.model_dump_json(indent=2),
                   "同じ出来事を言い換えただけの種の組をまとめてください。"]),
        ConsolidateDraft, system=_CONSOLIDATE_SYSTEM_PROMPT)
    if decided is None:
        return None
    merges = []
    merged: set[int] = set()
    for merge in decided.merges:
        numbers = set(merge.numbers)
        valid = (merge.text and len(numbers) >= 2 and not numbers & merged
                 and all(1 <= number <= len(numbered) for number in numbers)
                 and any(number <= len(fresh) for number in numbers))
        if not valid:
            continue
        merges.append(SeedMerge(ids=[numbered[number - 1].id for number in sorted(numbers)], text=merge.text))
        merged |= numbers
    return merges


def apply_merges(s: Session, merges: list[SeedMerge]) -> None:
    for merge in merges:
        for seed_id in merge.ids:
            s.delete(s.get_one(EventSeed, seed_id))
        s.add(EventSeed(text=merge.text, consolidated=True))
        logger.info(f"種{len(merge.ids)}件をまとめた: {merge.text}")
    s.flush()


def settle_seeds(s: Session, seed_ids: list[int]) -> None:
    for seed_id in seed_ids:
        s.get_one(EventSeed, seed_id).consolidated = True
    s.flush()


def seed_pool(s: Session) -> list[str]:
    """`draw_from` が引く元。id の順。"""
    return list(s.scalars(select(EventSeed.text).order_by(EventSeed.id)).all())


def draw_from(rng: random.Random, pool: list[str], count: int = constants.EVENT_SEED_DRAW_COUNT) -> list[str]:
    return rng.sample(pool, min(count, len(pool)))
