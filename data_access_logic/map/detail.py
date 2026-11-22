#!/usr/bin/env python3
"""場所の詳細マップの元データ。GUI の詳細マップ(`/maps/detail`)が描く。

詳細マップに出すのは、開いた場所から詳細の場所(`Location.map_detail`)だけをたどって届く子孫。詳細でない子
(全体の地図に出る場所)より下は、その子の詳細マップに出す。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.map.collect import (
    MapLocation, Planet, detail_children_of, map_location_of, parents_of, planet_of,
)
from data_access_logic.query import common_query
from db.schema import Location


class DetailMap(BaseModel):
    location: MapLocation
    # 物差しの縮尺に使う星。開いた場所か、一番近い上位の場所の星
    planet: Planet | None
    # 全体の地図に出る、開いた場所か一番近い上位の場所。全体の地図へ戻るときに真ん中に置く
    overall_id: int | None
    # 詳細の場所。開いた場所に近い段から、同じ段は id の順
    places: list[MapLocation]


def _on_overall_map(location: Location) -> bool:
    has_point = location.location_longitude is not None and location.location_latitude is not None
    return (not location.map_detail and location.location_planet is not None
            and (has_point or location.polygon is not None))


def _ancestry(s: Session, location: Location) -> list[Location]:
    """この場所から上へ、一番上の場所まで"""
    chain = [location]
    while chain[-1].parent_id is not None and all(row.id != chain[-1].parent_id for row in chain):
        parent = s.get(Location, chain[-1].parent_id)
        if parent is None:
            break
        chain.append(parent)
    return chain


def detail_map(s: Session, location_id: int) -> DetailMap:
    root = common_query.get_row(s, Location, location_id)
    places: list[Location] = []
    seen = {root.id}
    frontier = [root.id]
    while frontier:
        children = [child for child in s.scalars(
            select(Location)
            .where(Location.parent_id.in_(frontier), Location.map_detail.is_(True))
            .order_by(Location.id.asc())).all() if child.id not in seen]
        seen.update(child.id for child in children)
        places.extend(children)
        frontier = [child.id for child in children]

    ancestry = _ancestry(s, root)
    planet_id = next((row.location_planet for row in ancestry if row.location_planet is not None), None)
    planet_row = s.get(Location, planet_id) if planet_id is not None else None
    overall = next((row for row in ancestry if _on_overall_map(row)), None)

    parents = parents_of(s, [root, *places])
    counts = detail_children_of(s, seen)
    return DetailMap(
        location=map_location_of(root, parents, counts),
        planet=planet_of(planet_row) if planet_row is not None else None,
        overall_id=overall.id if overall is not None else None,
        places=[map_location_of(place, parents, counts) for place in places])
