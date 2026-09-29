#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import ListEntrypoint
from data_access_logic.query import common_query
from data_access_logic.story.reading import EventRow


class ListEvents(ListEntrypoint):
    def select(self):
        return common_query.events_select()

    def row(self, row) -> EventRow:
        return EventRow.model_validate(row)
