#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.step import db_step
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord
from db.schema import Story


@db_step
def commit_story(s: Session, form: StoryCreateForm) -> StoryRecord:
    CommitEntrypoint.check_exists(s, Story, form.parent_story_id, "parent_story_id")
    record = Story()
    form.write_to(record)
    s.add(record)
    CommitEntrypoint.finalize(s, record)
    return StoryRecord.model_validate(record)
