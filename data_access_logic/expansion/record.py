from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.orm import selectinload

from data_access_logic.material import Material, Timestamp
from db.schema import Expansion


class ExpansionRecord(Material):
    id: int
    mode: str
    prompt: str
    story_id: int | None = None
    actor_id: int | None = None
    time: Timestamp | None = None
    location_id: int | None = None
    status: str
    summary: str
    created_at: datetime


class ExpansionChangeRecord(Material):
    id: int
    table_name: str
    row_id: int
    op: str
    before: dict[str, Any] | None = None
    reason: str
    created_at: datetime


class ExpansionConflictRecord(Material):
    id: int
    expansion_id: int
    table_name: str
    row_id: int
    detail: str
    proposal: str
    status: str


class ExpansionDetail(ExpansionRecord):
    LOAD_OPTIONS: ClassVar[tuple] = (selectinload(Expansion.changes), selectinload(Expansion.conflicts))

    changes: list[ExpansionChangeRecord]
    conflicts: list[ExpansionConflictRecord]


class ExpansionCounts(BaseModel):
    added: int = 0
    updated: int = 0
    deleted: int = 0
    open_conflicts: int = 0


class ExpansionListItem(ExpansionRecord):
    counts: ExpansionCounts


class RevertedExpansion(BaseModel):
    id: int
    # 戻した変更の数
    reverted: int
