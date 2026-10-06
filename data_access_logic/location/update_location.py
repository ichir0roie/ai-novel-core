#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.form import LocationUpdateForm
from data_access_logic.location.parent import check_under_parent
from data_access_logic.location.record import LocationRecord
from data_access_logic.query import common_query
from db.child_lists import replaced_histories
from db.schema import Location, LocationHistory

_PLACEMENT = ("parent_id", "area", "start", "end")


class UpdateLocation(CommitEntrypoint):

    def __init__(self, location: LocationUpdateForm):
        self.location = location

    def execute(self, s: Session) -> LocationRecord:
        form = self.location
        record = common_query.get_row(s, Location, form.id)
        changed = form.model_fields_set
        # 置き場所に関わる欄を直さないなら検査しない(検査を足す前に入った行も、他の欄は直せるように)
        if changed & set(_PLACEMENT):
            after = {name: getattr(form if name in changed else record, name) for name in _PLACEMENT}
            check_under_parent(s, after["parent_id"], after["area"], after["start"], after["end"], location_id=record.id)
        form.write_changes_to(record)
        if form.histories is not None:
            record.histories = replaced_histories(record.histories, form.histories, LocationHistory, owner=record)
        self.finalize(s, record)
        return LocationRecord.model_validate(record)
