#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.location.record import DeletedLocation
from db.schema import Location


class DeletePlace(CommitDraft):
    model = Location

    def __init__(self, place_id: int):
        self.place_id = place_id

    def execute(self, session) -> DeletedLocation:
        record = self.get_or_raise(session, self.place_id, "場所")
        child = session.scalars(
            select(Location.id).where(Location.parent_id == record.id)).first()
        if child is not None:
            raise ValueError(f"place_id={self.place_id} には子の場所が残っている。先にそちらを消す")

        deleted = DeletedLocation.model_validate(record)
        session.delete(record)
        return deleted
