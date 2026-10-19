#!/usr/bin/env python3
"""文体の指示(`ai/instructions/style.py`)に足す、世界ごとの好みを db から読む。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.instructions import style
from db.schema import StylePreference, StyleScope


def read_style_extras(s: Session, scope: StyleScope) -> str:
    """効く範囲が `scope` の行を id の順につなぐ。行が無ければ空。"""
    return "\n".join(s.scalars(select(StylePreference.text).where(StylePreference.scope == scope.value)
                               .order_by(StylePreference.id)).all())


def writing_style(s: Session) -> str:
    """AI が書くすべての文の書き方。"""
    return style.writing_style_instruction(read_style_extras(s, StyleScope.ALL))


def episode_style(s: Session) -> str:
    """話の本文の書き方(すべての文の書き方に、本文だけの決まりを足したもの)。"""
    return style.style_instruction(read_style_extras(s, StyleScope.ALL), read_style_extras(s, StyleScope.EPISODE))
