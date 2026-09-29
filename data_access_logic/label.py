#!/usr/bin/env python3
"""一覧・参照先・レビューで行を呼ぶ名前。"""
from __future__ import annotations

from db.schema import Character, CharacterRelation, Episode, Event, Idea, Location, Meme, Oracle, Story

PREVIEW_LENGTH = 80

# 行を呼ぶ名前にする列。無い表(ミームなど)は本文の頭で呼ぶ
LABEL_COLUMNS: dict[type, str | None] = {
    Story: "name", Episode: "title", Character: "name", CharacterRelation: "relation", Event: "name",
    Location: "name", Idea: "name", Meme: None, Oracle: "title",
}


def clipped(text: str) -> str:
    return text[:PREVIEW_LENGTH] + ("…" if len(text) > PREVIEW_LENGTH else "")


def label_of(model: type, row) -> str:
    """`row` は `model` の ORM の行か、同じ名前の欄を持つレコードのモデル。"""
    column = LABEL_COLUMNS.get(model)
    if column:
        value = getattr(row, column)
        if value:
            return str(value)
    for name in getattr(model, "TEXT_COLUMNS", ()):
        value = (getattr(row, name) or "").strip()
        if value:
            return clipped(value.splitlines()[0])
    return f"id={row.id}"
