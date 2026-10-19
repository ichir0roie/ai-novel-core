#!/usr/bin/env python3
"""文体の好みの段(`data_access_logic/step.py`)。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.step import db_step
from data_access_logic.style_preference import extras


@db_step
def writing_style(s: Session) -> str:
    return extras.writing_style(s)
