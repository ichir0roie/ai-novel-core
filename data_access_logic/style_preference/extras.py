#!/usr/bin/env python3
"""文体の指示(`ai/instructions/style.py` の `style_instruction()`)に足す、世界ごとの好みを db から読む。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.schema import StylePreference


def read_style_extras(s: Session) -> str:
    """すべての行を id の順につなぐ。行が無ければ空。"""
    return "\n".join(s.scalars(select(StylePreference.text).order_by(StylePreference.id)).all())
