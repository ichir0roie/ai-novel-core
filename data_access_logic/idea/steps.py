#!/usr/bin/env python3
"""アイデアの db の段(`data_access_logic/step.py`)。web のセッション(`web_session/`)が API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.context import resolve_ideas as resolve
from data_access_logic.idea.form import IdeaCreateForm
from data_access_logic.idea.models import IdeaContextMaterial, IdeaDraft
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.step import RowId, db_step
from db.schema import Idea
from db.stamp import Stamp


class ResolveForm(BaseModel):
    # AI が挙げた、アイデアと照らす語
    keywords: list[IdeaDraft]
    location_id: int | None
    time: Stamp | None


@db_step
def resolve_ideas(s: Session, form: ResolveForm) -> IdeaContextMaterial:
    """当たらなかった造語は候補として足す(この段の終わりに確定する)。"""
    return resolve(s, form.keywords, form.location_id, form.time)


@db_step
def commit_idea(s: Session, form: IdeaCreateForm) -> IdeaRecord:
    return CommitIdea(form).execute(s)


@db_step
def idea_record(s: Session, form: RowId) -> IdeaRecord:
    return IdeaRecord.model_validate(s.get_one(Idea, form.id))
