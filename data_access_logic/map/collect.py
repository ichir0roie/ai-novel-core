#!/usr/bin/env python3
"""星ごとの地図の元データ。GUI の地図(`/maps`)と、場所の近く(`ListNeighbors`)が使う。"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.map.category import category_of
from data_access_logic.map.geometry import planet_radius_km
from data_access_logic.query import common_query
from db.schema import Location


class Planet(BaseModel):
    id: int
    name: str | None
    area: float | None
    radius_km: float | None


class MapLocation(BaseModel):
    id: int
    name: str | None
    kind: str | None
    # 地図の色分け(`data_access_logic/map/category.py`)
    category: str
    parent_id: int | None
    parent_name: str | None
    parent_kind: str | None
    lon: float | None
    lat: float | None
    alt: float | None
    polygon: dict[str, Any] | None
    environment: str | None
    sample_region: str | None
    sample_culture: str | None
    sample_era: str | None
    start: str | None
    end: str | None
    link: str


class PlanetMap(BaseModel):
    planet: Planet
    # 経緯度を持つ場所
    points: list[MapLocation]
    # 輪郭(polygon)を持つ場所
    shapes: list[MapLocation]


def _num(value: float | None) -> float | None:
    return None if value is None else float(value)


def planet_of(planet: Location) -> Planet:
    return Planet(id=planet.id, name=planet.name, area=_num(planet.area), radius_km=planet_radius_km(planet.area))


def parents_of(s: Session, locations: Iterable[Location]) -> dict[int, Location]:
    """場所の親を一度に引く。`Location.parent` は noload なので、識別マップに先に載った行では None のまま"""
    ids = {location.parent_id for location in locations if location.parent_id is not None}
    if not ids:
        return {}
    return {parent.id: parent for parent in s.scalars(select(Location).where(Location.id.in_(ids)))}


def map_location_of(location: Location, parents: dict[int, Location]) -> MapLocation:
    parent = parents.get(location.parent_id) if location.parent_id is not None else None
    return MapLocation(
        id=location.id, name=location.name, kind=location.kind, category=category_of(location.kind),
        parent_id=location.parent_id,
        parent_name=parent.name if parent else None,
        parent_kind=parent.kind if parent else None,
        lon=_num(location.location_longitude), lat=_num(location.location_latitude),
        alt=_num(location.location_altitude),
        polygon=location.polygon,
        environment=location.environment,
        sample_region=location.sample_region, sample_culture=location.sample_culture,
        sample_era=location.sample_era,
        start=str(location.start) if location.start else None,
        end=str(location.end) if location.end else None,
        link=f"/tables/location/{location.id}",
    )


def planet_maps(s: Session) -> list[PlanetMap]:
    # 星ごとに引くと、星の数だけ db を往復する(手元の踏み台越しでは一往復ごとに数十 ms かかる)
    on_planet: dict[int, list[Location]] = defaultdict(list)
    mapped = s.scalars(common_query.mapped_locations_select()).all()
    for location in mapped:
        on_planet[location.location_planet].append(location)
    parents = parents_of(s, mapped)
    result = []
    for planet in s.scalars(common_query.planets_select()).all():
        locations = on_planet.get(planet.id, [])
        points = [map_location_of(location, parents) for location in locations
                  if location.location_longitude is not None and location.location_latitude is not None]
        shapes = [map_location_of(location, parents) for location in locations if location.polygon is not None]
        if not points and not shapes:
            continue
        result.append(PlanetMap(planet=planet_of(planet), points=points, shapes=shapes))
    return result
