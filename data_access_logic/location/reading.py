from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.history_start import by_start
from data_access_logic.location.models import LocationLine
from data_access_logic.query import common_query
from db.schema import Location
from db.stamp import Stamp


def location_at(location: Location, time: Stamp) -> LocationLine:
    """`time` までに起きた来歴だけを付けた場所。場所の芯(`text`)は時期を限らないので、先のことは来歴の行に書けば、
    それより前の話・出来事には渡らない。"""
    return LocationLine(
        id=location.id, name=location.name, kind=location.kind, text=location.text, environment=location.environment,
        histories=sorted((history for history in location.histories if history.covers(time)),
                         key=by_start))


def location_path_at(s: Session, location_id: int, time: Stamp) -> list[LocationLine]:
    """最上位の場所から `location_id` までの道筋を、`time` の年までの来歴付きで。"""
    return [location_at(common_query.get_row(s, Location, step.id), time)
            for step in common_query.location_path(s, location_id)]
