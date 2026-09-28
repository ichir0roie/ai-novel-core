#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import func, select

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.polygon import parse_polygon
from db.schema import Location


class UpdatePlace(CommitDraft):
    model = Location

    def __init__(self, place: str | dict):
        self.place = place

    def execute(self, session) -> dict:
        data = self.parse(self.place)
        place_id = self.require_id(data, "直す対象の場所")
        self.check_columns(data)

        record = self.get_or_raise(session, place_id, "場所")

        if "area" in data:
            self._check_area(session, record, data["area"])
        if "polygon" in data:
            data["polygon"] = parse_polygon(data["polygon"])

        return self.apply(session, record, data)

    @staticmethod
    def _check_area(session, record: Location, area) -> None:
        if area is None or record.parent_id is None:
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
