#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.form import LocationUpdateForm
from data_access_logic.location.record import LocationRecord
from data_access_logic.query import common_query
from db.schema import Location


class UpdatePlace(CommitEntrypoint):
    model = Location

    def __init__(self, place: LocationUpdateForm):
        self.place = place

    def execute(self, session: Session) -> LocationRecord:
        record = common_query.get_row(session, Location, self.place.id)
        if self.place.area is not None:
            self._check_area(session, record, self.place.area)
        self.place.write_changes_to(record)
        self.finalize(session, record)
        return LocationRecord.model_validate(record)

    @staticmethod
    def _check_area(session: Session, record: Location, area: float) -> None:
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
