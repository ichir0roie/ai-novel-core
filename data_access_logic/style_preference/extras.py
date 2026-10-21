#!/usr/bin/env python3
"""AI に書かせる文の指示(db の `style_preference` と、作品・話の `instruction`)を、使う所の範囲に合わせて読む。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from db.schema import Episode, Story, StylePreference, StyleScope


def _scope_text(s: Session, scope: StyleScope) -> str:
    return s.scalar(select(StylePreference.text).where(StylePreference.scope == scope.value)) or ""


def style_text(s: Session, scope: StyleScope, story_id: int | None = None, episode_id: int | None = None) -> str:
    """使う所の範囲 `scope` に効く指示を、全体の行 → 作品の指示(祖先の作品から順に) → その範囲の行 → 話の指示 の順につなぐ。
    空の指示は足さない。"""
    story_path = common_query.story_path_ids(s, story_id) if story_id is not None else []
    stories = {story.id: story.instruction for story in s.scalars(select(Story).where(Story.id.in_(story_path)))}
    parts = [
        _scope_text(s, StyleScope.ALL),
        *(stories.get(each, "") for each in story_path),
        _scope_text(s, scope) if scope != StyleScope.ALL else "",
        (s.scalar(select(Episode.instruction).where(Episode.id == episode_id)) or "") if episode_id is not None else "",
    ]
    return "\n\n".join(part.strip() for part in parts if part.strip())


def instruction_text(s: Session, scope: StyleScope) -> str:
    """仕事ごとの指示の行。行が無ければ空。"""
    return _scope_text(s, scope)


def writing_style(s: Session, scope: StyleScope = StyleScope.ALL, story_id: int | None = None,
                  episode_id: int | None = None) -> str:
    """AI が文を書くときの書き方。"""
    return style_text(s, scope, story_id, episode_id)


def episode_style(s: Session, story_id: int | None = None, episode_id: int | None = None) -> str:
    """話の本文の書き方。"""
    return style_text(s, StyleScope.EPISODE, story_id, episode_id)
