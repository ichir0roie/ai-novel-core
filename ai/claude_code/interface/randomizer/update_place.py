#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import func, select

from ai.claude_code.interface.randomizer._base import CommitDraft
from data_access_logic.location.form import LocationUpdateForm
from data_access_logic.location.record import LocationRecord
from db.schema import Location


class UpdatePlace(CommitDraft):
    model = Location

    def __init__(self, place: LocationUpdateForm):
        self.place = place

    def execute(self, session) -> LocationRecord:
        record = self.get_or_raise(session, self.place.id, "場所")
        if self.place.area is not None:
            self._check_area(session, record, self.place.area)
        self.apply(session, record, self.place.changed_column_values(Location))
        return LocationRecord.model_validate(record)

    @staticmethod
    def _check_area(session, record: Location, area: float) -> None:
        if record.parent_id is None:
            return
        parent = session.get(Location, record.parent_id)
        if parent is None or parent.area is None:
            return
        if not area < parent.area:
            raise ValueError(
                f"area={area} が親(id={record.parent_id})の広さ {parent.area} 未満でない")

        siblings_area = session.scalar(
            select(func.coalesce(func.sum(Location.area), 0))
            .where(Location.parent_id == record.parent_id, Location.id != record.id))
        if float(siblings_area) + area > float(parent.area):  # DECIMAL 列の合計は Decimal で返る
            raise ValueError(
                f"area={area} を足すと、親(id={record.parent_id})の広さ "
                f"{parent.area} を兄弟(自分を除く)の合計 {siblings_area} が超える")
