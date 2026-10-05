from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.query import common_query, world_creation_query
from db.schema import Location
from db.stamp import Stamp


def check_under_parent(
        s: Session, parent_id: int | None, area: float | None, start: Stamp | None, end: Stamp | None,
        location_id: int | None = None) -> None:
    """場所を `parent_id` の下に置けるか。`location_id` は直すときの自分の id(自分と兄弟の合計から除く)。"""
    if parent_id is None:
        return
    parent = s.get(Location, parent_id)
    if parent is None:
        raise UnknownRecordError(f"parent_id={parent_id} という id の location が見つからない")
    if location_id is not None and parent_id in common_query.descendant_location_ids(s, location_id):
        raise ValueError(f"parent_id={parent_id} は id={location_id} 自身かその下位の場所なので、親にすると循環する")
    _check_area(s, parent, area, location_id)
    world_creation_query.check_within_parent_span(parent, start, end, "location")


def _check_area(s: Session, parent: Location, area: float | None, location_id: int | None) -> None:
    if area is None or parent.area is None:
        return
    area = float(area)  # DECIMAL 列の値は Decimal で返り、float と足せない
    if not area < parent.area:
        raise ValueError(
            f"area={area} が親(id={parent.id})の広さ {parent.area} 未満でない")

    siblings_area = s.scalar(world_creation_query.siblings_area_sum_select(parent.id, exclude_id=location_id))
    if float(siblings_area) + area > float(parent.area):
        raise ValueError(
            f"area={area} を足すと、親(id={parent.id})の広さ {parent.area} を"
            f"兄弟の合計 {siblings_area} が超える")
