#!/usr/bin/env python3
"""世界の展開を新しい順に並べる。展開ごとに、足した・直した・消した行の数と、残っている食い違いの数を添える。

    ListExpansions(limit=20, mode="character").show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.expansion.record import ExpansionCounts, ExpansionListItem, ExpansionRecord
from data_access_logic.query import expansion_query


class ListExpansions(SessionEntrypoint):
    def __init__(self, limit: int = 50, status: str | None = None, mode: str | None = None,
                 actor_id: int | None = None):
        self.limit = limit
        self.status = status
        self.mode = mode
        self.actor_id = actor_id

    def execute(self, s: Session) -> list[ExpansionListItem]:
        rows = s.scalars(expansion_query.expansions_select(self.limit, self.status, self.mode, self.actor_id)).all()
        ids = [row.id for row in rows]
        changes = expansion_query.change_counts(s, ids)
        conflicts = expansion_query.open_conflict_counts(s, ids)
        return [ExpansionListItem(
            **ExpansionRecord.model_validate(row).model_dump(),
            counts=ExpansionCounts(
                added=changes.get(row.id, {}).get("add", 0), updated=changes.get(row.id, {}).get("update", 0),
                deleted=changes.get(row.id, {}).get("delete", 0), open_conflicts=conflicts.get(row.id, 0)),
        ) for row in rows]
