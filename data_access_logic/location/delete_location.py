#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.record import DeletedLocation
from data_access_logic.query import common_query
from db.schema import Location


class DeleteLocation(CommitEntrypoint):
    model = Location

    def __init__(self, location_id: int):
        self.location_id = location_id

    def execute(self, s: Session) -> DeletedLocation:
        record = common_query.get_row(s, Location, self.location_id)
        child = s.scalars(
            select(Location.id).where(Location.parent_id == record.id)).first()
        if child is not None:
            raise ValueError(f"location_id={self.location_id} には子の場所が残っている。先にそちらを消す")

        deleted = DeletedLocation.model_validate(record)
        s.delete(record)
        return deleted
