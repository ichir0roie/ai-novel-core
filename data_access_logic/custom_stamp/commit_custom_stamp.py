#!/usr/bin/env python3
"""暦を足す入口。作品の `custom_stamp_id` に付けると、その作品と子孫の作品の時刻をこの暦で数える。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.custom_stamp import writing
from data_access_logic.custom_stamp.form import CustomStampCreateForm
from data_access_logic.custom_stamp.record import CustomStampRecord
from data_access_logic.entrypoint import CommitEntrypoint
from db.schema import CustomStamp


class CommitCustomStamp(CommitEntrypoint):
    def __init__(self, custom_stamp: CustomStampCreateForm):
        self.custom_stamp = custom_stamp

    def execute(self, s: Session) -> CustomStampRecord:
        record = CustomStamp(months=[])
        record.name = self.custom_stamp.name
        record.hours_per_day = self.custom_stamp.hours_per_day
        record.minutes_per_hour = self.custom_stamp.minutes_per_hour
        record.seconds_per_minute = self.custom_stamp.seconds_per_minute
        record.days_per_week = self.custom_stamp.days_per_week
        writing.write_offset(record, self.custom_stamp.offset)
        writing.write_months(record, self.custom_stamp.months)
        writing.check(record)
        s.add(record)
        self.finalize(s, record)
        return CustomStampRecord.model_validate(record)
