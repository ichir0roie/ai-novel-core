#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.record import DeletedLocation
from data_access_logic.query import common_query
from db.schema import Location


class DeletePlace(CommitEntrypoint):
    model = Location

    def __init__(self, place_id: int):
        self.place_id = place_id

    def execute(self, s: Session) -> DeletedLocation:
        record = common_query.get_row(s, Location, self.place_id)
        child = s.scalars(
            select(Location.id).where(Location.parent_id == record.id)).first()
        if child is not None:
            raise ValueError(f"place_id={self.place_id} には子の場所が残っている。先にそちらを消す")

        deleted = DeletedLocation.model_validate(record)
        s.delete(record)
        return deleted
