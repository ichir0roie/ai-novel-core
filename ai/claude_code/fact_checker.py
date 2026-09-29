#!/usr/bin/env python3
"""`local_ai`(Ollama)はネットを引けないので、ここだけは claude_ai 固有。

Dラボの MCP のサーバー名は環境ごとに違う(`claude mcp list` で見る)ので、許可ルールを
`DEM_CLAUDE_AI_DLAB_TOOLS` で差し替えられるようにしている。繋がっていなければ AI はネット検索だけで検める。
"""
from __future__ import annotations

import os
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select

from ai.claude_code import ai_client
from ai.instructions.sensitive import FACT_CHECK_BIO_INSTRUCTION
from data_access_logic.meme.extractor import refresh as refresh_memes
from data_access_logic.source_text import SourceBatch, SourceBatchSerialized, SourceText, batches
from db.schema import Idea, Meme, Oracle, Session

WEB_TOOLS = ("WebSearch", "WebFetch", "ToolSearch")
DEFAULT_DLAB_TOOLS = "mcp__d-lab"
# 検索を何度も挟むので、道具なしの呼び出しより長く待つ。
TIMEOUT = 900.0
# 一度の呼び出しで検めさせる本文の字数の上限。一件でこれを超えるものは一件だけで渡す。
BATCH_LETTERS = 3000

# 検証結果は本文の末尾にこの見出しの節として持つ(別の列は持たない)。空ならまだ検めていない。
FACT_CHECK_HEADING = "# 検証結果"
_FACT_CHECK_SECTION = re.compile(r"\n*^#[ \t]*検証結果[ \t]*\n.*\Z", re.M | re.S)


def strip_fact_check(text: str | None) -> str:
    """本文から検証結果の節を取り除いた、素の本文を返す。"""
    return _FACT_CHECK_SECTION.sub("", text or "").rstrip()


def _append_fact_check(text: str | None, fact_check: str) -> str:
    base = strip_fact_check(text)
    return f"{base}\n\n{FACT_CHECK_HEADING}\n{fact_check}" if base else f"{FACT_CHECK_HEADING}\n{fact_check}"


_SYSTEM_PROMPT = f"""\
あなたは創作の設定を検める、科学・歴史・思想に詳しい校閲者です。
小説の世界の設定(アイデア)か、著者の創作・AI についての覚え書き(oracle)か、人物の行動原理の芯になる考え方(ミーム)を番号つきの JSON で渡すので、\
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

MODELS = {"idea": Idea, "oracle": Oracle, "meme": Meme}


def tools() -> tuple[str, ...]:
    dlab = os.environ.get("DEM_CLAUDE_AI_DLAB_TOOLS", DEFAULT_DLAB_TOOLS)
    return WEB_TOOLS + tuple(tool.strip() for tool in dlab.split(",") if tool.strip())


_Checked = Idea | Oracle | Meme


def _source(record: _Checked) -> SourceText[_Checked]:
    """前に検めた結果は外して、素の本文だけを検めさせる。"""
    text = strip_fact_check(record.text)
    if isinstance(record, Idea):
        return SourceText(row=record, label=f"アイデア「{record.name}」(種類: {record.kind})", text=text)
    if isinstance(record, Oracle):
        return SourceText(row=record, label="覚え書き(oracle)", text=text)
    return SourceText(row=record, label=f"ミーム(分類: {record.category or '未分類'})", text=text)


def targets(session: Session, table: str, ids: list[int] | None = None, limit: int | None = None) -> list:
    model = MODELS[table]
    query = select(model).order_by(model.id)
    if ids is not None:
        query = query.where(model.id.in_(ids))
    else:
        query = query.where(~model.text.contains(FACT_CHECK_HEADING), model.text != "")
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query).all())


def check(session: Session, table: str, ids: list[int] | None = None, limit: int | None = None) -> int:
    records = targets(session, table, ids, limit)
    written = 0
    for batch in batches([_source(record) for record in records], BATCH_LETTERS):
        decided = ai_client.try_generate_json(
            "\n".join([SourceBatchSerialized.model_validate(SourceBatch(sources=batch)).model_dump_json(indent=2),
                       "それぞれをDラボのナレッジとネット検索で検め、妥当性と補足を書いてください。"]),
            FactChecksDraft.model_json_schema(), system=_SYSTEM_PROMPT, timeout=TIMEOUT, tools=tools())
        try:
            results = FactChecksDraft.model_validate(decided).results
        except ValidationError:
            continue
        for result in results:
            if not (1 <= result.number <= len(batch) and result.fact_check):
                continue
            record = batch[result.number - 1].row
            record.text = _append_fact_check(record.text, result.fact_check)
            # 検証結果もミームの元になるので、抜き出し直させる
            if not isinstance(record, Meme):
                record.meme_seeded = False
            written += 1
        session.commit()
    if records:
        print(f"[claude_code/fact_checker] {table} {len(records)}件のうち、{written}件を検めた")
    return written


def last_meme_id(session: Session) -> int:
    return session.scalar(select(func.max(Meme.id))) or 0


def check_new_memes(session: Session, last_id: int) -> int:
    """`last_id` より後に足したミームだけを検める(既にあるミームの後埋めは `check` を名指しなしで呼ぶ)。"""
    ids = list(session.scalars(select(Meme.id).where(Meme.id > last_id)).all())
    return check(session, "meme", ids=ids) if ids else 0


def check_and_extract(session: Session, table: str, ids: list[int] | None = None, limit: int | None = None) -> dict:
    """検めたあと、ミームの元(アイデア・oracle)なら本文(検証結果の節を含む)からミームを抜き出し、足したミームも検める。"""
    checked = check(session, table, ids, limit)
    if table == "meme":
        return {"checked": checked, "memes_added": 0}
    last_id = last_meme_id(session)
    added = refresh_memes(session, ai_client)
    check_new_memes(session, last_id)
    return {"checked": checked, "memes_added": added}
