#!/usr/bin/env python3
"""ミームどうし・元との関係は持たない(移り変わり・伝染していくため)。元の側の `meme_seeded` で抜き出し済みかだけを持つ。"""
from __future__ import annotations

import logging
import random
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.instructions.sensitive import BIO_ABSTRACTION_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.meme.models import (
    ClassifyDraft, ClassifyRequestSerialized, DedupeDraft, DedupeRequestSerialized,
    DrawnMeme, MemeDraft, MemesDraft, MemeText,
)
from data_access_logic.query import meme_query
from data_access_logic.source_text import SourceBatchSerialized, SourceText, batches, plot_section
from db.schema import MEME_CATEGORIES, Character, ConfirmStatus, Event, Idea, Meme, Oracle

logger = logging.getLogger(__name__)

CATEGORY_DESCRIPTIONS = {
    "信条": "何を大事にし、どう振る舞うか。一人の行動の型",
    "欲求": "何を求めて動くか",
    "境遇": "特定の状況に置かれたときの葛藤・選択",
    "集団": "国・組織・集団として働く論理",
    "理": "世界の法則や代償。誰かが持つ考え方ではない",
}

_CATEGORY_GUIDE = "\n".join(f"  - {name}: {CATEGORY_DESCRIPTIONS[name]}" for name in MEME_CATEGORIES)

_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
用語の説明(アイデア)・著者の創作についての覚え書き・それらの検証結果・人物の筋書き・起きた出来事を、番号つきの JSON で渡すので、それぞれから、\
人物の行動原理の芯になりうる「ミーム」(繰り返し現れる考え方・価値観・行動の型)を抜き出してください。
- 人名・地名・組織名・その作品だけの固有名詞を抜き、他の人物にも乗り移りうる普遍的な考え方として書く。
- 一つのミームは一文。何を大事にし、何を避け、何をきっかけに動くかが分かるように書く。
- 固有名詞を抜いても特定の人物の役どころ・筋書き上の境遇をなぞるだけのもの(その人物にしか当てはまらない立場や状況)は抜き出さない。引いた人物がその人物の写しになるため。
- 作者の前書き・使用環境・書き方の約束など、考え方にならない文からは抜き出さない。
- 出来事からは、当事者がその出来事を経て選んだこと・手放したこと・行き着いた考え方だけを抜き出す。起きたことをなぞっただけの記録からは抜き出さない。
- 本文中の「検証結果」の節は、用語の説明や覚え書きを現実の科学・歴史・思想・心理学に照らした調べ書き。\
そこに出てくる現実の人・集団の考え方や、研究で裏付けられた行動の傾向を、人物の行動原理になりうる考え方として抜き出す。\
出典の一覧や、妥当性の判定そのものからは抜き出さない。
- 一つの元から 0〜3 件。同じ元の中で似たミームは一つにまとめる。
- それぞれに、次の分類から一つを振る。
{_CATEGORY_GUIDE}
{BIO_ABSTRACTION_INSTRUCTION}"""

_DEDUPE_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を「新しいミーム」と「既にあるミーム」に分けて渡すので、新しいミームのうち、\
既にあるミームか、それより前の番号の新しいミームと同じ考え方を言い換えただけのものを見つけてください。
- 何を大事にし、何をきっかけに、どう動くかがほぼ同じものだけを重複とする。題材が近いだけで、大事にするものや動き方が違うものは重複にしない。
- 重複が無ければ duplicates は空のリストにする。"""

_CLASSIFY_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を番号つきで渡すので、それぞれに次の分類から一つを振ってください。
{_CATEGORY_GUIDE}"""

_MemeSource = Idea | Oracle | Character | Event


def _pending(s: Session) -> list[SourceText[_MemeSource]]:
    """アイデア・oracle の本文には検証結果(`# 検証結果` の節)も含む。人物は `# plot` の節だけを使う。"""
    sources: list[SourceText[_MemeSource]] = []
    for idea in s.scalars(meme_query.unseeded_select(Idea)).all():
        sources.append(SourceText(row=idea, label="アイデア", text=idea.text))
    for oracle in s.scalars(meme_query.unseeded_select(Oracle)).all():
        sources.append(SourceText(row=oracle, label="覚え書き", text=oracle.text))
    for character in s.scalars(meme_query.unseeded_select(Character)).all():
        sources.append(SourceText(row=character, label="人物の筋書き", text=plot_section(character.text)))
    for event in s.scalars(meme_query.unseeded_select(Event)).all():
        sources.append(SourceText(row=event, label="出来事", text=event.text))
    return [source for source in sources if source.text.strip()]


def _normalized(text: str) -> str:
    return re.sub(r"[\s。、]", "", text)


def _without_duplicates(s: Session, ai: AIClient, candidates: list[MemeDraft]) -> list[MemeDraft] | None:
    """答えが得られなければ None(元を抜き出し直す)。"""
    existing = list(s.scalars(select(Meme).order_by(Meme.id)).all())
    seen = {_normalized(meme.text) for meme in existing}
    fresh = []
    for candidate in candidates:
        if _normalized(candidate.text) not in seen:
            seen.add(_normalized(candidate.text))
            fresh.append(candidate)

    existing_sources = [SourceText(row=meme, label="ミーム", text=meme.text) for meme in existing]
    for chunk in batches(existing_sources, constants.MEME_DEDUPE_LETTERS) or [[]]:
        if not fresh or (not chunk and len(fresh) < 2):
            break
        request = DedupeRequestSerialized(fresh=[candidate.text for candidate in fresh],
                                          existing=[MemeText(text=source.text) for source in chunk])
        decided = ai.generate(
            "\n".join([request.model_dump_json(indent=2),
                       "新しいミームのうち、重複しているものの番号を挙げてください。"]),
            DedupeDraft, system=_DEDUPE_SYSTEM_PROMPT, timeout=constants.MEME_TIMEOUT)
        if decided is None:
            return None
        duplicates = set(decided.duplicates)
        for number in sorted(duplicates):
            if 1 <= number <= len(fresh):
                logger.info(f"既にあるミームと重なるので足さない: {fresh[number - 1].text}")
        fresh = [candidate for number, candidate in enumerate(fresh, start=1) if number not in duplicates]
    return fresh


def _classify(s: Session, ai: AIClient) -> int:
    unclassified = list(s.scalars(select(Meme).where(Meme.category.is_(None)).order_by(Meme.id)).all())
    sources = [SourceText(row=meme, label="ミーム", text=meme.text) for meme in unclassified]
    for batch in batches(sources, constants.MEME_BATCH_LETTERS):
        request = ClassifyRequestSerialized(memes=[MemeText(text=source.text) for source in batch])
        decided = ai.generate(
            "\n".join([request.model_dump_json(indent=2),
                       "それぞれのミームに分類を振ってください。"]),
            ClassifyDraft, system=_CLASSIFY_SYSTEM_PROMPT, timeout=constants.MEME_TIMEOUT)
        if decided is None:
            continue
        for item in decided.categories:
            if 1 <= item.number <= len(batch) and item.category in MEME_CATEGORIES:
                batch[item.number - 1].row.category = item.category
        s.commit()
    classified = sum(1 for meme in unclassified if meme.category)
    if unclassified:
        logger.info(f"分類の空いたミーム{len(unclassified)}件のうち、{classified}件に分類を振った")
    return classified


def refresh(s: Session, ai: AIClient) -> int:
    """抜き出せなかった元は `meme_seeded` を false のまま残し、次の回に抜き出し直す。足したミームの件数を返す。"""
    pending = _pending(s)
    added = 0
    for batch in batches(pending, constants.MEME_BATCH_LETTERS):
        decided = ai.generate(
            "\n".join([SourceBatchSerialized(sources=batch).model_dump_json(indent=2),
                       "それぞれの元からミームを抜き出してください。"]),
            MemesDraft, system=_SYSTEM_PROMPT, timeout=constants.MEME_TIMEOUT)
        if decided is None:
            logger.warning(f"元{len(batch)}件からミームを抜き出せなかった。次の回に抜き出し直す")
            continue
        fresh = _without_duplicates(s, ai, decided.memes)
        if fresh is None:
            logger.warning(f"元{len(batch)}件から抜き出したミームの重複を確かめられなかった。次の回に抜き出し直す")
            continue
        for candidate in fresh:
            s.add(Meme(text=candidate.text, category=candidate.known_category))
            added += 1
        for source in batch:
            source.row.meme_seeded = True
        s.commit()
    if pending:
        logger.info(f"元{len(pending)}件から抜き出し、ミームを{added}件足した")
    _classify(s, ai)
    return added


def draw(s: Session, rng: random.Random, categories: tuple[str, ...]) -> list[DrawnMeme]:
    """分類ごとに `constants.MEME_DRAW_RANGE` の件数を引き、それぞれにその人物の中での置き場所をランダムに振る。"""
    drawn = []
    for category in categories:
        memes = list(s.scalars(
            select(Meme).where(Meme.category == category, Meme.confirmed == ConfirmStatus.APPROVED).order_by(Meme.id)
        ).all())
        count = min(rng.randint(*constants.MEME_DRAW_RANGE), len(memes))
        for meme in rng.sample(memes, count):
            drawn.append(DrawnMeme(id=meme.id, position=rng.choice(list(constants.MEME_POSITIONS)),
                                   category=meme.category, text=meme.text))
    return drawn


def position_legend() -> str:
    return " / ".join(f"{position}={meaning}" for position, meaning in constants.MEME_POSITIONS.items())
