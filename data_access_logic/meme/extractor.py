#!/usr/bin/env python3
"""ミームどうし・元との関係は持たない(移り変わり・伝染していくため)。抜き出すのは、本文を渡して確定した話の本文だけ
(覚え書き・出来事・推敲した本文からも抜くと、似たミームばかり増えるので)。
ミームどうしで持つのは、反転した対(アンチミーム、`anti_meme_id`)だけ。抜き出すときに対で作り、対の無いミームには後から作る。

db だけの段(`sources_of` / `meme_texts` / `save_memes` / `unpaired_sources` / `save_anti_memes` /
`unclassified_sources` / `save_categories` / `meme_pool`)と、
AI だけの段(`extraction_draft` → `without_duplicates`、`anti_draft`、`classify_draft`)に分けてある。
流れ(`data_access_logic/flows/meme.py`)がつなぐ。
"""
from __future__ import annotations

import logging
import random
import re

from sqlalchemy import ColumnElement, false, select, true
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.meme.models import (
    AntiMeme, AntisDraft, ClassifyDraft, DedupeDraft, DedupeRequestSerialized,
    DrawnMeme, MemeCategory, MemeDraft, MemesDraft, MemeText, NumberedMemesSerialized, PooledMeme,
)
from data_access_logic.source_text import (
    SourceBatchSerialized, SourceRow, SourceText, batches, row_of, source_of, strip_fact_check,
)
from db import writer
from db.schema import MEME_CATEGORIES, Episode, Meme, Origin, StyleScope
from db.writer import Writer

logger = logging.getLogger(__name__)

CATEGORY_DESCRIPTIONS = {
    "信条": "何を大事にし、どう振る舞うか。一人の行動の型",
    "欲求": "何を求めて動くか",
    "境遇": "特定の状況に置かれたときの葛藤・選択",
    "集団": "国・組織・集団として働く論理",
    "理": "世界の法則や代償。誰かが持つ考え方ではない",
}

_CATEGORY_GUIDE = "\n".join(f"  - {name}: {CATEGORY_DESCRIPTIONS[name]}" for name in MEME_CATEGORIES)

_EXTRACT_SYSTEM = """\
話の本文を番号つきで渡すので、それぞれから、人物の行動原理の芯になりうる「ミーム」(繰り返し現れる考え方・価値観・行動の型)を抜き出す。
- 人名・地名・組織名・その作品だけの固有名詞を抜き、他の人物にも乗り移りうる普遍的な考え方として書く。
- 一つのミームは一文(40字以内を目安)。何を大事にし、何をきっかけにどう動くかを書く。
- 特定の人物にしか当てはまらない立場や境遇をなぞるだけのものは抜き出さない。
- 人物がその話で選んだこと・手放したこと・行き着いた考え方だけを抜き出す。起きたことをなぞっただけの所からは抜き出さない。
- 誰にでも当てはまり、人物ごとの動き方を分けない考え方は抜き出さない。
- 一つの本文から 0〜2 件。はっきりしたものが無ければ 0 件でよい。同じ本文の中で似たミームは一つにまとめる。
- それぞれに、渡す分類から一つを振る。
- それぞれに、反転したアンチミームを一つ添える。"""

_DEDUPE_SYSTEM = """\
人物の行動原理になる「ミーム」を「新しいミーム」と「既にあるミーム」に分けて渡すので、新しいミームのうち、既にあるミームか、それより前の番号の新しいミームと同じ考え方を言い換えただけのものを見つける。
- 何を大事にし、何をきっかけに、どう動くかがほぼ同じものだけを重複とする。題材が近いだけで、大事にするものや動き方が違うものは重複にしない。
- 重複が無ければ duplicates は空のリストにする。"""

_ANTI_SYSTEM = "人物の行動原理になる「ミーム」を番号つきで渡すので、それぞれを反転したアンチミームを一つずつ書く。"

_CLASSIFY_SYSTEM = "人物の行動原理になる「ミーム」を番号つきで渡すので、それぞれに渡す分類から一つを振る。"


def sources_of(s: Session, rows: list[SourceRow]) -> list[SourceText]:
    """渡した話の本文。本文が空の話は外す。"""
    sources: list[SourceText] = []
    for row in rows:
        record = row_of(s, row.table, row.id)
        if not isinstance(record, Episode):
            raise ValueError(f"ミームを抜き出す元は話(episode)の本文だけ: {row.table!r}")
        source = source_of(record, "話の本文", record.main_text or "")
        if source.text.strip():
            sources.append(source)
    return sources


def meme_texts(s: Session) -> list[str]:
    """既にあるミームの文面(検証結果の節は除く。重複を見るのに要らず、AI に渡す字数を膨らませる)。id の順。"""
    return [strip_fact_check(text) for text in s.scalars(select(Meme.text).order_by(Meme.id)).all()]


def extraction_draft(ai: AIClient, batch: list[SourceText]) -> MemesDraft | None:
    return ai.generate(
        "\n".join([SourceBatchSerialized(sources=batch).model_dump_json(indent=2),
                   f"分類:\n{_CATEGORY_GUIDE}",
                   "それぞれの元からミームを抜き出す。"]),
        MemesDraft, system=_EXTRACT_SYSTEM, style_scope=StyleScope.MEME)


def _normalized(text: str) -> str:
    return re.sub(r"[\s。、]", "", text)


def without_duplicates(ai: AIClient, candidates: list[MemeDraft], existing: list[str]) -> list[MemeDraft] | None:
    """`existing`(既にあるミーム)と同じ考え方の候補を外す。答えが得られなければ None(元を抜き出し直す)。"""
    seen = {_normalized(text) for text in existing}
    fresh = []
    for candidate in candidates:
        key = _normalized(candidate.text)
        if key not in seen:
            seen.add(key)
            fresh.append(candidate)

    for chunk in batches([MemeText(text=text) for text in existing], constants.MEME_DEDUPE_LETTERS) or [[]]:
        if not fresh or (not chunk and len(fresh) < 2):
            break
        request = DedupeRequestSerialized(fresh=[candidate.text for candidate in fresh], existing=chunk)
        decided = ai.generate(
            "\n".join([request.model_dump_json(indent=2),
                       "新しいミームのうち、重複しているものの番号を挙げる。"]),
            DedupeDraft, system=_DEDUPE_SYSTEM, style_scope=None)
        if decided is None:
            return None
        duplicates = set(decided.duplicates)
        for number in sorted(duplicates):
            if 1 <= number <= len(fresh):
                logger.info(f"既にあるミームと重なるので足さない: {fresh[number - 1].text}")
        fresh = [candidate for number, candidate in enumerate(fresh, start=1) if number not in duplicates]
    return fresh


def _pair(s: Session, meme: Meme, anti_text: str) -> Meme:
    anti = Meme(text=anti_text, category=meme.category)
    s.add(anti)
    s.flush()
    meme.anti_meme_id = anti.id
    anti.anti_meme_id = meme.id
    return anti


def save_memes(s: Session, memes: list[MemeDraft]) -> int:
    """ミームとアンチミームを対で足す。足した件数(アンチミームを含む)を返す。"""
    for candidate in memes:
        meme = Meme(text=candidate.text, category=candidate.known_category)
        s.add(meme)
        s.flush()
        _pair(s, meme, candidate.anti_text)
    s.flush()
    return len(memes) * 2


def _writable() -> ColumnElement[bool]:
    """書き手(`db/writer.py`)が直してよいミーム。分類・対を振るのは今あるミームを直すことなので、AI の書き手は AI の行だけ、
    人物モードはどれも直さない(作者の行は、作者が回す `RefreshGeneratedContent` で振る)。"""
    state = writer.current()
    if state.writer is Writer.AI_APPEND:
        return false()
    if state.by_ai:
        return Meme.origin == Origin.AI
    return true()


def _meme_sources(s: Session, condition: ColumnElement[bool]) -> list[SourceText]:
    memes = s.scalars(select(Meme).where(condition, _writable()).order_by(Meme.id)).all()
    return [source_of(meme, "ミーム", strip_fact_check(meme.text)) for meme in memes]


def unpaired_sources(s: Session) -> list[SourceText]:
    """アンチミームの無いミーム。GUI で手で足したもの、アンチミームを作る前からあったもの。"""
    return _meme_sources(s, Meme.anti_meme_id.is_(None))


def anti_draft(ai: AIClient, batch: list[SourceText]) -> list[AntiMeme] | None:
    request = NumberedMemesSerialized(memes=[MemeText(text=source.text) for source in batch])
    decided = ai.generate(
        "\n".join([request.model_dump_json(indent=2),
                   "それぞれのミームのアンチミームを書く。"]),
        AntisDraft, system=_ANTI_SYSTEM, style_scope=StyleScope.MEME)
    if decided is None:
        return None
    return [AntiMeme(id=batch[item.number - 1].id, text=item.anti_text)
            for item in decided.antis if 1 <= item.number <= len(batch) and item.anti_text]


def save_anti_memes(s: Session, antis: list[AntiMeme]) -> int:
    """対の無いミームにアンチミームを足す。間に対ができた(GUI で直したなど)ミームには足さない。"""
    added = 0
    for item in antis:
        meme = s.get_one(Meme, item.id)
        if meme.anti_meme_id is not None:
            continue
        _pair(s, meme, item.text)
        added += 1
    s.flush()
    return added


def unclassified_sources(s: Session) -> list[SourceText]:
    return _meme_sources(s, Meme.category.is_(None))


def classify_draft(ai: AIClient, batch: list[SourceText]) -> list[MemeCategory] | None:
    request = NumberedMemesSerialized(memes=[MemeText(text=source.text) for source in batch])
    decided = ai.generate(
        "\n".join([request.model_dump_json(indent=2),
                   f"分類:\n{_CATEGORY_GUIDE}",
                   "それぞれのミームに分類を振る。"]),
        ClassifyDraft, system=_CLASSIFY_SYSTEM, style_scope=None)
    if decided is None:
        return None
    return [MemeCategory(id=batch[item.number - 1].id, category=item.category)
            for item in decided.categories if 1 <= item.number <= len(batch) and item.category in MEME_CATEGORIES]


def save_categories(s: Session, categories: list[MemeCategory]) -> int:
    for item in categories:
        s.get_one(Meme, item.id).category = item.category
    s.flush()
    return len(categories)


def meme_pool(s: Session, categories: tuple[str, ...]) -> list[PooledMeme]:
    """`draw_from` が引く元。id の順。検証結果の節は引いた人物に要らないので落としておく(web では API で運ぶ)。"""
    memes = s.scalars(select(Meme).where(Meme.category.in_(categories)).order_by(Meme.id)).all()
    return [PooledMeme(id=meme.id, category=meme.category, text=strip_fact_check(meme.text)) for meme in memes]


def draw_from(rng: random.Random, pool: list[PooledMeme], categories: tuple[str, ...]) -> list[DrawnMeme]:
    """分類ごとに `constants.MEME_DRAW_RANGE` の件数を引き、それぞれにその人物の中での置き場所をランダムに振る。"""
    drawn = []
    for category in categories:
        memes = [meme for meme in pool if meme.category == category]
        count = min(rng.randint(*constants.MEME_DRAW_RANGE), len(memes))
        for meme in rng.sample(memes, count):
            drawn.append(DrawnMeme(id=meme.id, position=rng.choice(list(constants.MEME_POSITIONS)),
                                   category=meme.category, text=meme.text))
    return drawn


def draw(s: Session, rng: random.Random, categories: tuple[str, ...]) -> list[DrawnMeme]:
    return draw_from(rng, meme_pool(s, categories), categories)


def position_legend() -> str:
    return " / ".join(f"{position}={meaning}" for position, meaning in constants.MEME_POSITIONS.items())
