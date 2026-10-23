#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.step import db_step
from data_access_logic.style_preference import extras
from data_access_logic.style_preference.form import WritingStyleForm


@db_step
def writing_style(s: Session, form: WritingStyleForm) -> str:
    return extras.writing_style(s, form.scope, form.story_id, form.episode_id)
