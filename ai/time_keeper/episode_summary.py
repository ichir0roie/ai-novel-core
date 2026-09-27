#!/usr/bin/env python3
from __future__ import annotations

import json

from sqlalchemy import select

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from db.schema import Episode, EpisodeSummary, Session, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者です。
話の本文を一話ぶん渡すので、次の話を書く作家へ渡す覚え書きを作ってください。
summary には、誰が何をして何がどうなったか、次の話へ引き継ぐ筋と、人物の立場・関係の変わりようを書いてください。
style には、地の文と会話の混ぜ方・一文の長さ・視点の置き方・語り口の癖を、真似できる言い方で書いてください。
どちらも本文を写さず、四〜六文にまとめてください。
JSON で答えてください。キーは summary と style の二つだけ。"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "style": {"type": "string"},
    },
    "required": ["summary", "style"],
    "additionalProperties": False,
}


def summarize(session: Session, episode: Episode, ai: AIClient) -> dict | None:
    """話(`Episode`)の本文を要約する。覚え書きは話の行に付ける。"""
    text = episode.text.strip()
    if not text:
        return None
    digest = summary_source_hash(text)
    row = session.scalars(
        select(EpisodeSummary).where(EpisodeSummary.episode_id == episode.id)).first()
    if row is not None and row.source_hash == digest:
        return {"summary": row.summary, "style": row.style}

    source = {"id": episode.id, "title": episode.title, "text": text}
    decided = ai.try_generate_json(
        f"話: {json.dumps(source, ensure_ascii=False)}\nこの話の概要と文体を覚え書きにしてください。",
        _SCHEMA, system=_SYSTEM_PROMPT, timeout=constants.RECAP_TIMEOUT)
    note = {key: (decided.get(key) or "").strip() for key in ("summary", "style")}
    if not all(note.values()):
        return None
    if row is None:
        row = EpisodeSummary(story_id=episode.story_id, episode_id=episode.id)
        session.add(row)
    row.source_hash = digest
    row.summary = note["summary"]
    row.style = note["style"]
    session.commit()
    return note
