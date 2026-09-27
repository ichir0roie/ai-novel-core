#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story._base import StoryCommit
from db.schema import Plot
from db.schema_pydantic import to_dict


class SetPlotSynced(StoryCommit):
    model = Plot

    def __init__(self, plot_id: int, synced: bool = True):
        self.plot_id = plot_id
        self.synced = synced

    def execute(self, session) -> dict:
        record = session.get(Plot, int(self.plot_id))
        if record is None:
            raise UnknownRecordError(f"id={self.plot_id} という話が見つからない")
        record.synced = bool(self.synced)
        return to_dict(record)
