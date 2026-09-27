#!/usr/bin/env python3
"""種別(kind)を書かずに手で足されたアイデアの種別を、AI に決めさせる。"""
from __future__ import annotations

from sqlalchemy import select

from ai.time_keeper._ai import AIClient
from ai.time_keeper.idea_search import DEFAULT_KIND
from db.schema import Idea, Session

_SYSTEM_PROMPT = """\
あなたは物語の設定資料の編集者です。
渡すアイデア(世界の設定資料の一項目)の種別を一つ決めてください。
- 既にある種別のうち当てはまるものがあれば、それをそのまま使う。
- 当てはまるものが無いときだけ、「技術」「制度」「概念」のような短い語で新しく付ける。
- 置き場所(ディレクトリ)は分類の手がかりだが、種別と一致するとは限らない。名前と本文の中身で決める。
JSON で答えてください。キーは kind だけ。"""

_SCHEMA = {
    "type": "object",
    "properties": {"kind": {"type": "string"}},
    "required": ["kind"],
    "additionalProperties": False,
}


def judge(session: Session, name: str | None, text: str | None, ai: AIClient) -> str:
    kinds = session.scalars(select(Idea.kind).where(Idea.kind.is_not(None)).distinct().order_by(Idea.kind)).all()
    prompt = "\n".join([
        f"既にある種別: {'、'.join(kinds) or '(まだ無い)'}",
        f"名前: {name or ''}",
        "本文:",
        (text or "").strip(),
    ])
    result = ai.try_generate_json(prompt, _SCHEMA, system=_SYSTEM_PROMPT)
    kind = result.get("kind")
    return kind.strip() if isinstance(kind, str) and kind.strip() else DEFAULT_KIND
