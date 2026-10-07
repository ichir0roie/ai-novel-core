#!/usr/bin/env python3
"""ミームどうし・元との関係は持たない(移り変わり・伝染していくため)。元の側の `meme_seeded` で抜き出し済みかだけを持つ。
ミームどうしで持つのは、反転した対(アンチミーム、`anti_meme_id`)だけ。抜き出すときに対で作り、対の無いミームには後から作る。

db だけの段(`pending_sources` / `meme_texts` / `save_memes` / `unpaired_sources` / `save_anti_memes` /
`unclassified_sources` / `save_categories` / `meme_pool`)と、
AI だけの段(`extraction_draft` → `without_duplicates`、`anti_draft`、`classify_draft`)に分けてある。
流れ(`data_access_logic/flows/meme.py`)がつなぐ。
"""
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
    AntiMeme, AntisDraft, ClassifyDraft, DedupeDraft, DedupeRequestSerialized,
    DrawnMeme, MemeCategory, MemeDraft, MemesDraft, MemeText, NumberedMemesSerialized, PooledMeme,
)
from data_access_logic.query import meme_query
from data_access_logic.source_text import SourceBatchSerialized, SourceText, batches, row_of, source_of, strip_fact_check
from db.schema import MEME_CATEGORIES, Episode, Event, Meme, Oracle

logger = logging.getLogger(__name__)

CATEGORY_DESCRIPTIONS = {
    "信条": "何を大事にし、どう振る舞うか。一人の行動の型",
    "欲求": "何を求めて動くか",
    "境遇": "特定の状況に置かれたときの葛藤・選択",
    "集団": "国・組織・集団として働く論理",
    "理": "世界の法則や代償。誰かが持つ考え方ではない",
}

_CATEGORY_GUIDE = "\n".join(f"  - {name}: {CATEGORY_DESCRIPTIONS[name]}" for name in MEME_CATEGORIES)

# 長い一文は、引いた人物の行動原理に条件や筋書きまで持ち込むので、芯だけに絞らせる
_CONCISE_GUIDE = "一つのミームは一文で簡潔に書く(40字以内を目安)。何を大事にし、何をきっかけにどう動くかの芯だけを残し、条件・例・理由を重ねない。"

_ANTI_GUIDE = """アンチミームは、ミームを反転した考え方。ミームが大事にするものを退け、避けるものを選ぶ。
  - 「〜しない」と打ち消しただけの文にせず、それだけで一つの行動原理として立つように書く。
  - ミームと同じ分類に収まるように書く(理なら、その法則が逆に働く世界の理として書く)。
  - ミームと同じく一文で簡潔に書く(40字以内を目安)。"""

_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
著者の創作についての覚え書き・その検証結果・起きた出来事・話の本文を、番号つきの JSON で渡すので、それぞれから、\
人物の行動原理の芯になりうる「ミーム」(繰り返し現れる考え方・価値観・行動の型)を抜き出してください。
- 人名・地名・組織名・その作品だけの固有名詞を抜き、他の人物にも乗り移りうる普遍的な考え方として書く。
- {_CONCISE_GUIDE}
- 固有名詞を抜いても特定の人物の役どころ・筋書き上の境遇をなぞるだけのもの(その人物にしか当てはまらない立場や状況)は抜き出さない。引いた人物がその人物の写しになるため。
- 作者の前書き・使用環境・書き方の約束など、考え方にならない文からは抜き出さない。
- 出来事と話の本文からは、当事者がその出来事を経て選んだこと・手放したこと・行き着いた考え方だけを抜き出す。起きたことをなぞっただけの記録からは抜き出さない。
- 本文中の「検証結果」の節は、覚え書きを現実の科学・歴史・思想・心理学に照らした調べ書き。\
そこに出てくる現実の人・集団の考え方や、研究で裏付けられた行動の傾向を、人物の行動原理になりうる考え方として抜き出す。\
出典の一覧や、妥当性の判定そのものからは抜き出さない。
- 一つの元から 0〜3 件。同じ元の中で似たミームは一つにまとめる。
- それぞれに、次の分類から一つを振る。
{_CATEGORY_GUIDE}
- それぞれに、反転したアンチミームを一つ添える。
{_ANTI_GUIDE}
{BIO_ABSTRACTION_INSTRUCTION}"""

_DEDUPE_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を「新しいミーム」と「既にあるミーム」に分けて渡すので、新しいミームのうち、\
既にあるミームか、それより前の番号の新しいミームと同じ考え方を言い換えただけのものを見つけてください。
- 何を大事にし、何をきっかけに、どう動くかがほぼ同じものだけを重複とする。題材が近いだけで、大事にするものや動き方が違うものは重複にしない。
- 重複が無ければ duplicates は空のリストにする。"""

_ANTI_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を番号つきで渡すので、それぞれを反転したアンチミームを一つずつ書いてください。
{_ANTI_GUIDE}
{BIO_ABSTRACTION_INSTRUCTION}"""

_CLASSIFY_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を番号つきで渡すので、それぞれに次の分類から一つを振ってください。
{_CATEGORY_GUIDE}"""

def pending_sources(s: Session) -> list[SourceText]:
    """まだミームを抜き出していない元。oracle の本文には検証結果(`# 検証結果` の節)も含む。
    アイデアの本文と人物の筋書きからは抜き出さず、話の本文から抜き出す。"""
    sources: list[SourceText] = []
    for oracle in s.scalars(meme_query.unseeded_select(Oracle, Oracle.text)).all():
        sources.append(source_of(oracle, "覚え書き", oracle.text))
    for event in s.scalars(meme_query.unseeded_select(Event, Event.text)).all():
        sources.append(source_of(event, "出来事", event.text))
    for episode in s.scalars(meme_query.unseeded_select(Episode, Episode.main_text)).all():
        sources.append(source_of(episode, "話の本文", episode.main_text))
    return sources


def meme_texts(s: Session) -> list[str]:
    """既にあるミームの文面(検証結果の節は除く。重複を見るのに要らず、AI に渡す字数を膨らませる)。id の順。"""
    return [strip_fact_check(text) for text in s.scalars(select(Meme.text).order_by(Meme.id)).all()]


def extraction_draft(ai: AIClient, batch: list[SourceText]) -> MemesDraft | None:
    return ai.generate(
        "\n".join([SourceBatchSerialized(sources=batch).model_dump_json(indent=2),
                   "それぞれの元からミームを抜き出してください。"]),
        MemesDraft, system=_SYSTEM_PROMPT)


def _normalized(text: str) -> str:
    return re.sub(r"[\s。、]", "", text)


def without_duplicates(ai: AIClient, candidates: list[MemeDraft], existing: list[str]) -> list[MemeDraft] | None:
    """`existing`(既にあるミーム)と同じ考え方の候補を外す。答えが得られなければ None(元を抜き出し直す)。"""
    seen = {_normalized(text) for text in existing}
    fresh = []
    for candidate in candidates:
        if _normalized(candidate.text) not in seen:
            seen.add(_normalized(candidate.text))
            fresh.append(candidate)

    for chunk in batches([MemeText(text=text) for text in existing], constants.MEME_DEDUPE_LETTERS) or [[]]:
        if not fresh or (not chunk and len(fresh) < 2):
            break
        request = DedupeRequestSerialized(fresh=[candidate.text for candidate in fresh], existing=chunk)
        decided = ai.generate(
            "\n".join([request.model_dump_json(indent=2),
                       "新しいミームのうち、重複しているものの番号を挙げてください。"]),
            DedupeDraft, system=_DEDUPE_SYSTEM_PROMPT)
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


def save_memes(s: Session, memes: list[MemeDraft], sources: list[SourceText]) -> int:
    """ミームとアンチミームを対で足し、元に抜き出し済みの印を付ける。足した件数(アンチミームを含む)を返す。"""
    for candidate in memes:
        meme = Meme(text=candidate.text, category=candidate.known_category)
        s.add(meme)
        s.flush()
        _pair(s, meme, candidate.anti_text)
    for source in sources:
        row_of(s, source.table, source.id).meme_seeded = True
    s.flush()
    return len(memes) * 2


def unpaired_sources(s: Session) -> list[SourceText]:
    """アンチミームの無いミーム。GUI で手で足したもの、アンチミームを作る前からあったもの。"""
    memes = s.scalars(select(Meme).where(Meme.anti_meme_id.is_(None)).order_by(Meme.id)).all()
    return [source_of(meme, "ミーム", strip_fact_check(meme.text)) for meme in memes]


def anti_draft(ai: AIClient, batch: list[SourceText]) -> list[AntiMeme] | None:
    request = NumberedMemesSerialized(memes=[MemeText(text=source.text) for source in batch])
    decided = ai.generate(
        "\n".join([request.model_dump_json(indent=2),
                   "それぞれのミームのアンチミームを書いてください。"]),
        AntisDraft, system=_ANTI_SYSTEM_PROMPT)
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
    memes = s.scalars(select(Meme).where(Meme.category.is_(None)).order_by(Meme.id)).all()
    return [source_of(meme, "ミーム", strip_fact_check(meme.text)) for meme in memes]


def classify_draft(ai: AIClient, batch: list[SourceText]) -> list[MemeCategory] | None:
    request = NumberedMemesSerialized(memes=[MemeText(text=source.text) for source in batch])
    decided = ai.generate(
        "\n".join([request.model_dump_json(indent=2),
                   "それぞれのミームに分類を振ってください。"]),
        ClassifyDraft, system=_CLASSIFY_SYSTEM_PROMPT)
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
