#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.form import LocationCreateForm
from data_access_logic.location.record import LocationRecord
from data_access_logic.query import world_creation_query
from db.schema import Location


class CommitPlace(CommitEntrypoint):
    model = Location

    def __init__(self, place: LocationCreateForm):
        self.place = place

    def execute(self, session: Session) -> LocationRecord:
        self.check_exists(session, Location, self.place.parent_id, "parent_id")
        if self.place.parent_id is not None:
            parent = session.get_one(Location, self.place.parent_id)
            self._check_area(session, parent, self.place.area)
            world_creation_query.check_within_parent_span(
                parent, self.place.start, self.place.end, "location")

        record = Location()
        self.place.write_to(record)
        session.add(record)
        self.finalize(session, record)
        return LocationRecord.model_validate(record)

    @staticmethod
    def _check_area(session: Session, parent: Location, area: float | None) -> None:
        if area is None or parent.area is None:
            return
        if not area < parent.area:
            raise ValueError(
                f"area={area} が親(id={parent.id})の広さ {parent.area} 未満でない")

        siblings_area = session.scalar(
            world_creation_query.siblings_area_sum_select(parent.id))
        if float(siblings_area) + area > float(parent.area):  # DECIMAL 列の合計は Decimal で返る
            raise ValueError(
                f"area={area} を足すと、親(id={parent.id})の広さ {parent.area} を"
                f"兄弟の合計 {siblings_area} が超える")
