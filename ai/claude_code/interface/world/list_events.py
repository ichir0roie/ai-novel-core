#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story._rows import EventRow
from ai.claude_code.interface.world._base import WorldQuery
from data_access_logic.query import common_query


class ListEvents(WorldQuery):
    def select(self):
        return common_query.events_select()

    def row(self, row) -> EventRow:
        return EventRow.model_validate(row)
