#!/usr/bin/env python3
"""Dラボの MCP のサーバー名は環境ごとに違う(`claude mcp list` で見る)ので、許可ルールを
`DEM_CLAUDE_AI_DLAB_TOOLS` で差し替えられるようにしている。繋がっていなければ AI はネット検索だけで検める。

db だけの段(`check_sources` / `save_fact_checks` / `last_meme_id` / `new_meme_ids`)と、AI だけの段(`check_draft`)に分けてある。
手元では `check` などがつなぎ、web のセッションでは `web_session/fact_check.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging
import os

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from ai.instructions.sensitive import FACT_CHECK_BIO_INSTRUCTION
from data_access_logic.ai_client import AIClient
from data_access_logic.meme.extractor import refresh as refresh_memes
from data_access_logic.material import Material
from data_access_logic.source_text import (
    FACT_CHECK_HEADING, SourceBatchSerialized, SourceText, batches, row_of, source_of, strip_fact_check,
)
from db.schema import Meme, Oracle, Session

logger = logging.getLogger(__name__)

WEB_TOOLS = ("WebSearch", "WebFetch", "ToolSearch")
DEFAULT_DLAB_TOOLS = "mcp__d-lab"
# 検索を何度も挟むので、道具なしの呼び出し(既定 600 秒)より長く待つ。
TIMEOUT = 900.0
# 一度の呼び出しで検めさせる本文の字数の上限。一件でこれを超えるものは一件だけで渡す。
BATCH_LETTERS = 3000

def _append_fact_check(text: str | None, fact_check: str) -> str:
    base = strip_fact_check(text)
    return f"{base}\n\n{FACT_CHECK_HEADING}\n{fact_check}" if base else f"{FACT_CHECK_HEADING}\n{fact_check}"


_SYSTEM_PROMPT = f"""\
あなたは創作の設定を検める、科学・歴史・思想に詳しい校閲者です。
著者の創作・AI についての覚え書き(oracle)か、人物の行動原理の芯になる考え方(ミーム)を番号つきの JSON で渡すので、\
それぞれをDラボのナレッジとネット検索で調べ、内容の妥当性を検め、書き手の役に立つ補足を書いてください。
- Dラボのナレッジ検索(search_dlab_knowledge。見当たらなければ ToolSearch で「dlab」を探す)が使えるなら、\
  必ず先にそれで調べる。心理学・行動科学・脳科学・健康・人間関係・社会・AI に関わる内容は特に、Dラボの知見を軸にする。\
  Dラボで足りない部分と、物理・天文・歴史などの事実はネット検索で補う。
- 架空の世界の設定なので、架空であること自体は誤りとしない。現実の科学・技術・歴史・社会・思想に照らして、\
  ありえる点・無理のある点、設定の中での食い違いを挙げる。
- 補足には、現実で近いもの(実在の現象・技術・制度・歴史上の出来事・思想や心理学の知見)と、\
  設定を厚くするのに使える事実を書く。
- ミームは、現実にその考え方を持った人・集団・思想の系譜や、心理学・社会学での裏付けを挙げる。
- 覚え書き(oracle)は、書かれた創作論・AI の使い方・物の見方が、現実の研究や実践に照らして妥当かを検め、裏付けや反論を挙げる。
- 検めた結果は、あとで人物の行動原理(ミーム)を抜き出す元にもなる。現実の人・集団がどう考え、どう動いたかを具体的に書く。
- 検索で確かめた事実だけを書き、分からないことは分からないと書く。
- 各 fact_check は次の三つの小見出しを持つ markdown にする。見出しは必ず `##` を使い、`#` 一つの見出しは使わない。
  ## 妥当性
  ## 補足
  ## 出典
  出典は `- [題](URL)` の箇条書きにする。Dラボの動画・記事は題の頭に「Dラボ: 」を付ける。
- 全体で 400〜800 字を目安にする。
{FACT_CHECK_BIO_INSTRUCTION}"""


class FactCheckDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="番号")
    fact_check: str = Field(description="検めた結果の markdown")

    @field_validator("fact_check")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


class FactChecksDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    results: list[FactCheckDraft] = Field(description="番号ごとの検めた結果")


class FactCheckNote(Material):
    """検めた結果を本文の末尾に足す行。"""

    table: str
    id: int
    fact_check: str


class FactChecked(BaseModel):
    checked: int
    memes_added: int


MODELS = {"oracle": Oracle, "meme": Meme}


def tools() -> tuple[str, ...]:
    dlab = os.environ.get("DEM_CLAUDE_AI_DLAB_TOOLS", DEFAULT_DLAB_TOOLS)
    return WEB_TOOLS + tuple(tool.strip() for tool in dlab.split(",") if tool.strip())


_Checked = Oracle | Meme


def _source(record: _Checked) -> SourceText:
    """前に検めた結果は外して、素の本文だけを検めさせる。"""
    text = strip_fact_check(record.text)
    if isinstance(record, Oracle):
        return source_of(record, "覚え書き(oracle)", text)
    return source_of(record, f"ミーム(分類: {record.category or '未分類'})", text)


def check_sources(s: Session, table: str, ids: list[int] | None = None, limit: int | None = None) -> list[SourceText]:
    """`ids` を渡さなければ、まだ検めていない行。"""
    model = MODELS[table]
    query = select(model).order_by(model.id)
    if ids is not None:
        query = query.where(model.id.in_(ids))
    else:
        query = query.where(~model.text.contains(FACT_CHECK_HEADING), model.text != "")
    if limit is not None:
        query = query.limit(limit)
    return [_source(record) for record in s.scalars(query).all()]


def check_draft(ai: AIClient, batch: list[SourceText]) -> list[FactCheckNote] | None:
    decided = ai.generate(
        "\n".join([SourceBatchSerialized(sources=batch).model_dump_json(indent=2),
                   "それぞれをDラボのナレッジとネット検索で検め、妥当性と補足を書いてください。"]),
        FactChecksDraft, system=_SYSTEM_PROMPT, timeout=TIMEOUT, tools=tools())
    if decided is None:
        return None
    return [FactCheckNote(table=batch[result.number - 1].table, id=batch[result.number - 1].id,
                          fact_check=result.fact_check)
            for result in decided.results if 1 <= result.number <= len(batch) and result.fact_check]


def save_fact_checks(s: Session, notes: list[FactCheckNote]) -> int:
    for note in notes:
        record = row_of(s, note.table, note.id)
        record.text = _append_fact_check(record.text, note.fact_check)
        # 検証結果もミームの元になるので、抜き出し直させる
        if not isinstance(record, Meme):
            record.meme_seeded = False
    s.flush()
    return len(notes)


def check(s: Session, ai: AIClient, table: str, ids: list[int] | None = None, limit: int | None = None) -> int:
    sources = check_sources(s, table, ids, limit)
    written = 0
    for batch in batches(sources, BATCH_LETTERS):
        notes = check_draft(ai, batch)
        if notes is None:
            continue
        written += save_fact_checks(s, notes)
        s.commit()
    if sources:
        logger.info(f"{table} {len(sources)}件のうち、{written}件を検めた")
    return written


def last_meme_id(s: Session) -> int:
    return s.scalar(select(func.max(Meme.id))) or 0


def new_meme_ids(s: Session, last_id: int) -> list[int]:
    return list(s.scalars(select(Meme.id).where(Meme.id > last_id)).all())


def check_new_memes(s: Session, ai: AIClient, last_id: int) -> int:
    """`last_id` より後に足したミームだけを検める(既にあるミームの後埋めは `check` を名指しなしで呼ぶ)。"""
    ids = new_meme_ids(s, last_id)
    return check(s, ai, "meme", ids=ids) if ids else 0


def extract_memes(s: Session, ai: AIClient, fact_check: bool) -> int:
    """ミームを抜き出し、`fact_check` なら足したミームも検める。足したミームの件数を返す。"""
    last_id = last_meme_id(s)
    added = refresh_memes(s, ai)
    if fact_check:
        check_new_memes(s, ai, last_id)
    return added


def check_and_extract(
    s: Session, ai: AIClient, table: str, ids: list[int] | None = None, limit: int | None = None,
) -> FactChecked:
    """検めたあと、ミームの元(oracle)なら本文(検証結果の節を含む)からミームを抜き出し、足したミームも検める。"""
    checked = check(s, ai, table, ids, limit)
    if table == "meme":
        return FactChecked(checked=checked, memes_added=0)
    return FactChecked(checked=checked, memes_added=extract_memes(s, ai, fact_check=True))
