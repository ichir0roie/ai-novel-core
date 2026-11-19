#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.step import db_step
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import ScopeRecord, StoryRecord
from data_access_logic.story.scope import args_scope_in
from db.schema import Story


@db_step
def commit_story(s: Session, form: StoryCreateForm) -> StoryRecord:
    CommitEntrypoint.check_exists(s, Story, form.parent_story_id, "parent_story_id")
    record = Story()
    form.write_to(record)
    s.add(record)
    CommitEntrypoint.finalize(s, record)
    return StoryRecord.model_validate(record)


class ScopeForm(BaseModel):
    # 入口の引数と同じ形で、作品を決める欄(`character_id` など)を渡す
    args: dict[str, Any]


@db_step
def read_scope(s: Session, form: ScopeForm) -> ScopeRecord:
    """流れの中で決まった行(人物モードが引いた人物など)の作品と暦。流れはこれを立て直して、その先の時刻を読み書きする。"""
    found = args_scope_in(s, form.args)
    return ScopeRecord.of(found)
