#!/usr/bin/env python3
"""暦を直す入口。時刻は西暦のまま db にあるので、直すと、この暦の作品の時刻の見え方(桁)が変わる。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.custom_stamp import writing
from data_access_logic.custom_stamp.form import CustomStampUpdateForm
from data_access_logic.custom_stamp.record import CustomStampRecord
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CustomStamp


class UpdateCustomStamp(CommitEntrypoint):
    def __init__(self, custom_stamp: CustomStampUpdateForm):
        self.custom_stamp = custom_stamp

    def execute(self, s: Session) -> CustomStampRecord:
        form = self.custom_stamp
        record = common_query.get_row(s, CustomStamp, form.id)
        fields = form.model_fields_set
        for name in ("name", "hours_per_day", "minutes_per_hour", "seconds_per_minute", "days_per_week"):
            if name in fields and getattr(form, name) is not None:
                setattr(record, name, getattr(form, name))
        if "offset" in fields and form.offset is not None:
            writing.write_offset(record, form.offset)
        if "months" in fields and form.months is not None:
            writing.write_months(record, form.months)
        writing.check(record)
        self.finalize(s, record)
        return CustomStampRecord.model_validate(record)
