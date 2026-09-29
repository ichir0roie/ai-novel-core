#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.entrypoint import ListEntrypoint
from data_access_logic.event.reading import EventRow
from data_access_logic.query import common_query
from db.schema import Event


class ListEvents(ListEntrypoint):
    def select(self):
        return common_query.events_select()

    def row(self, row: Event) -> EventRow:
        return EventRow.model_validate(row)
