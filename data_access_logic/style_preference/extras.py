#!/usr/bin/env python3
"""文体の指示(`ai/instructions/style.py` の `style_instruction()`)に足す、世界ごとの好みを db から読む。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.style_preference.form import StyleTarget
from db.schema import StylePreference


class StyleExtras(BaseModel):
    shared: str
    own: str


def _text(s: Session, target: StyleTarget) -> str:
    return s.scalar(select(StylePreference.text).where(StylePreference.target == target)) or ""


def read_style_extras(s: Session, target: StyleTarget) -> StyleExtras:
    return StyleExtras(shared=_text(s, StyleTarget.SHARED), own=_text(s, target))
