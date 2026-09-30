#!/usr/bin/env python3
"""作品の db の段(`data_access_logic/step.py`)。web のセッション(`web_session/`)が API 越しに呼ぶ。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.step import db_step
from data_access_logic.story.commit_story import CommitStory
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord


@db_step
def commit_story(s: Session, form: StoryCreateForm) -> StoryRecord:
    return CommitStory(form).execute(s)
