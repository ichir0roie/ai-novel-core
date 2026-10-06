#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.form import LocationCreateForm
from data_access_logic.location.parent import check_under_parent
from data_access_logic.location.record import LocationRecord
from db.child_lists import replaced_histories
from db.schema import Location, LocationHistory


class CommitLocation(CommitEntrypoint):

    def __init__(self, location: LocationCreateForm):
        self.location = location

    def execute(self, s: Session) -> LocationRecord:
        form = self.location
        check_under_parent(s, form.parent_id, form.area, form.start, form.end)

        record = Location()
        form.write_to(record)
        s.add(record)
        # 来歴の既定の知る相手はこの場所なので、先に id を決める
        s.flush()
        record.histories = replaced_histories([], form.histories, LocationHistory, owner=record)
        self.finalize(s, record)
        return LocationRecord.model_validate(record)
