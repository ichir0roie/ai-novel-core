#!/usr/bin/env python3
"""文体の好みの段(`data_access_logic/step.py`)。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.step import db_step
from data_access_logic.style_preference import extras
from data_access_logic.style_preference.form import InstructionForm, WritingStyleForm


@db_step
def writing_style(s: Session, form: WritingStyleForm) -> str:
    return extras.writing_style(s, form.scope, form.story_id, form.episode_id)


@db_step
def instruction(s: Session, form: InstructionForm) -> str:
    return extras.instruction_text(s, form.scope)
