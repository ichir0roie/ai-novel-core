#!/usr/bin/env python3
"""AI に書かせる文の書き方(db の `style_preference`)を、使う所の範囲に合わせて読む。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.instructions.style import EPISODE_LAYOUT_INSTRUCTION
from data_access_logic.query import common_query
from db.schema import StylePreference, StyleScope

_WIDE_SCOPES = (StyleScope.ALL, StyleScope.STORY)


def scopes_for(scope: StyleScope) -> tuple[StyleScope, ...]:
    """使う所の範囲 `scope` に効く範囲を、広い順に。全体 → ストーリー → その範囲。"""
    return _WIDE_SCOPES[:_WIDE_SCOPES.index(scope) + 1] if scope in _WIDE_SCOPES else (*_WIDE_SCOPES, scope)


def style_text(s: Session, scope: StyleScope, story_id: int | None = None) -> str:
    """使う所の範囲 `scope` に効く行を、全体 → ストーリー → その範囲の順につなぐ。同じ範囲の中は id の順。
    ストーリーの行は、`story_id` の作品と祖先の作品の行だけを、祖先から順に足す。"""
    scopes = scopes_for(scope)
    story_path = common_query.story_path_ids(s, story_id) if story_id is not None else []
    rows = [row for row in s.scalars(
        select(StylePreference).where(StylePreference.scope.in_([each.value for each in scopes]))
        .order_by(StylePreference.id)).all()
        if row.scope != StyleScope.STORY or row.story_id in story_path]
    rows.sort(key=lambda row: (scopes.index(StyleScope(row.scope)),
                               story_path.index(row.story_id) if row.scope == StyleScope.STORY else 0, row.id))
    return "\n\n".join(row.text.strip() for row in rows if row.text.strip())


def writing_style(s: Session, scope: StyleScope = StyleScope.ALL, story_id: int | None = None) -> str:
    """AI が文を書くときの書き方。"""
    return style_text(s, scope, story_id)


def episode_style(s: Session, story_id: int | None = None) -> str:
    """話の本文の書き方(本文の行に、場面の切れ目と行の組み方の約束を足したもの)。"""
    return "\n\n".join(part for part in (style_text(s, StyleScope.EPISODE, story_id), EPISODE_LAYOUT_INSTRUCTION) if part)
