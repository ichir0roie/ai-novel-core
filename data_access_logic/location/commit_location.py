#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.form import LocationCreateForm
from data_access_logic.location.parent import check_under_parent
from data_access_logic.location.record import LocationRecord
from db.child_lists import replaced_rows
from db.schema import Location, LocationHistory


class CommitLocation(CommitEntrypoint):

    def __init__(self, location: LocationCreateForm):
        self.location = location

    def execute(self, s: Session) -> LocationRecord:
        form = self.location
        check_under_parent(s, form.parent_id, form.area, form.start, form.end)

        record = Location()
        form.write_to(record)
        record.histories = replaced_rows([], form.histories, LocationHistory)
        s.add(record)
        self.finalize(s, record)
        return LocationRecord.model_validate(record)
