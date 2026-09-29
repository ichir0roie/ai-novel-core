#!/usr/bin/env python3
"""出来事の種は、元の本文から時代・場所・固有名詞を抜いたもの。出来事の生成(`GenerateEvent`)で候補を立てる手がかりに引く。"""
from __future__ import annotations

import logging
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.event_seed.models import ConsolidateDraft, ConsolidateRequestSerialized, SeedsDraft, SeedText
from data_access_logic.query import event_seed_query
from data_access_logic.source_text import SourceBatchSerialized, SourceText, batches, plot_section
from db.schema import Character, Episode, Event, EventSeed, Story

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
作品の筋書き・話の骨組み・人物の筋書き・起きた出来事を番号つきの JSON で渡すので、それぞれから、ほかの時代・ほかの場所・ほかの人物にも起こせる「出来事の種」を抜き出してください。
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

_SeedSource = Story | Episode | Character | Event


def _pending(s: Session) -> list[SourceText[_SeedSource]]:
    """話は種(`key`)を、無ければ本文を使う。人物は `# plot` の節だけを使う。"""
    sources: list[SourceText[_SeedSource]] = []
    for story in s.scalars(event_seed_query.unseeded_select(Story)).all():
        sources.append(SourceText(row=story, label="作品の筋書き", text=story.text))
    for episode in s.scalars(event_seed_query.unseeded_select(Episode)).all():
        sources.append(SourceText(row=episode, label="話の骨組み", text=episode.key.strip() or episode.text))
    for character in s.scalars(event_seed_query.unseeded_select(Character)).all():
        sources.append(SourceText(row=character, label="人物の筋書き", text=plot_section(character.text)))
    for event in s.scalars(event_seed_query.unseeded_select(Event)).all():
        sources.append(SourceText(row=event, label="出来事", text=event.text))
    return [source for source in sources if source.text.strip()]


def refresh(s: Session, ai: AIClient) -> int:
    """抜き出せなかった元は `event_seeded` を false のまま残し、次の回に抜き出し直す。足した種の件数を返す。"""
    pending = _pending(s)
    added = 0
    for batch in batches(pending, constants.EVENT_SEED_BATCH_LETTERS):
        decided = ai.generate(
            "\n".join([SourceBatchSerialized(sources=batch).model_dump_json(indent=2),
                       "それぞれの元から出来事の種を抜き出してください。"]),
            SeedsDraft, system=_SYSTEM_PROMPT, timeout=constants.EVENT_SEED_TIMEOUT)
        if decided is None:
            logger.warning(f"元{len(batch)}件から種を抜き出せなかった。次の回に抜き出し直す")
            continue
        s.add_all(EventSeed(text=seed) for seed in decided.seeds)
        added += len(decided.seeds)
        for source in batch:
            source.row.event_seeded = True
        s.commit()
    if pending:
        logger.info(f"元{len(pending)}件から抜き出し、種を{added}件足した")
    return added


def _merge(s: Session, ai: AIClient, fresh: list[EventSeed], settled: list[EventSeed]) -> list[EventSeed] | None:
    """まとめ残った新しい種を返す。答えが得られなければ None。"""
    numbered = [*fresh, *settled]
    request = ConsolidateRequestSerialized(fresh=[SeedText.model_validate(seed) for seed in fresh],
                                           settled=[SeedText.model_validate(seed) for seed in settled])
    decided = ai.generate(
        "\n".join([request.model_dump_json(indent=2),
                   "同じ出来事を言い換えただけの種の組をまとめてください。"]),
        ConsolidateDraft, system=_CONSOLIDATE_SYSTEM_PROMPT, timeout=constants.EVENT_SEED_TIMEOUT)
    if decided is None:
        return None
    merges = decided.merges
    merged: set[int] = set()
    for merge in merges:
        numbers = set(merge.numbers)
        valid = (merge.text and len(numbers) >= 2 and not numbers & merged
                 and all(1 <= number <= len(numbered) for number in numbers)
                 and any(number <= len(fresh) for number in numbers))
        if not valid:
            continue
        for number in numbers:
            s.delete(numbered[number - 1])
        s.add(EventSeed(text=merge.text, consolidated=True))
        merged |= numbers
        logger.info(f"種{len(numbers)}件をまとめた: {merge.text}")
    s.commit()
    return [seed for number, seed in enumerate(fresh, start=1) if number not in merged]


def _count(s: Session) -> int:
    return s.scalar(select(func.count(EventSeed.id))) or 0


def consolidate(s: Session, ai: AIClient) -> int:
    """棚卸し前の種が `constants.EVENT_SEED_CONSOLIDATE_EVERY` 件たまったら、似た種をまとめる。減った件数を返す。"""
    fresh = list(s.scalars(
        select(EventSeed).where(EventSeed.consolidated.is_(False)).order_by(EventSeed.id)).all())
    if len(fresh) < constants.EVENT_SEED_CONSOLIDATE_EVERY:
        return 0
    before = _count(s)
    settled = [SourceText(row=seed, label="種", text=seed.text) for seed in s.scalars(
        select(EventSeed).where(EventSeed.consolidated.is_(True)).order_by(EventSeed.id)).all()]
    for chunk in batches(settled, constants.EVENT_SEED_CONSOLIDATE_LETTERS) or [[]]:
        remaining = _merge(s, ai, fresh, [source.row for source in chunk])
        if remaining is None:
            logger.warning("棚卸しの答えが得られなかった。次の回にやり直す")
            return before - _count(s)
        fresh = remaining
    for seed in fresh:
        seed.consolidated = True
    s.commit()
    removed = before - _count(s)
    logger.info(f"棚卸しで種を{removed}件減らした(残り{before - removed}件)")
    return removed


def draw(s: Session, rng: random.Random, count: int = constants.EVENT_SEED_DRAW_COUNT) -> list[str]:
    seeds = s.scalars(select(EventSeed.text).order_by(EventSeed.id)).all()
    return rng.sample(list(seeds), min(count, len(seeds)))


def refresh_and_consolidate(s: Session, ai: AIClient) -> None:
    """出来事を足したあとに呼ぶ。種を抜き出していない元(足した出来事自身も含む)から種を足し、たまっていれば似た種をまとめる。"""
    refresh(s, ai)
    consolidate(s, ai)
