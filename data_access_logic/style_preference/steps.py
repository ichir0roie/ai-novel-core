#!/usr/bin/env python3
"""文体の好みの db の段(`data_access_logic/step.py`)。web のセッション(`web_session/`)が API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.step import db_step
from data_access_logic.style_preference.extras import StyleExtras, read_style_extras
from data_access_logic.style_preference.form import StyleTarget


class StyleTargetForm(BaseModel):
    target: StyleTarget


@db_step
def style_extras(s: Session, form: StyleTargetForm) -> StyleExtras:
    return read_style_extras(s, form.target)
