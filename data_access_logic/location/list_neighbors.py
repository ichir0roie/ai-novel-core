#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_serializer

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.map.collect import MapPlace, Planet, map_place_of, planet_of
from data_access_logic.map.geometry import (
    altitude_diff_text, angular_distance_deg, bearing_deg, bearing_name, distance_km, distance_text,
)
from data_access_logic.query import common_query
from db.schema import Location


class Neighbor(BaseModel):
    """地図の点の欄に、起点からの方角・距離・高低差を同じ段に並べて出す。"""

    point: MapPlace
    distance_deg: float
    distance_km: int | None = None
    bearing_deg: int
    bearing: str
    altitude_diff_m: float | None = None
    summary: str

    @model_serializer(mode="wrap")
    def _flat(self, handler: Any) -> dict:
        data = handler(self)
        return {**data.pop("point"), **data}


class Neighbors(BaseModel):
    place: MapPlace
    planet: Planet
    neighbors: list[Neighbor]


class ListNeighbors(SessionEntrypoint):
    def __init__(self, place_id: int, kind: str | None = None, limit: int | None = None):
        self.place_id = place_id
        self.kind = kind
        self.limit = limit

    def execute(self, session) -> Neighbors:
        origin = common_query.get_row(session, Location, self.place_id)
        if origin.location_longitude is None or origin.location_latitude is None:
            raise ValueError(f"{origin.name}(id={origin.id})は経緯度を持たない(面の場所か、座標が未記入)")
        planet_row = session.get(Location, origin.location_planet) if origin.location_planet is not None else None
        if planet_row is None:
            raise ValueError(f"{origin.name}(id={origin.id})は星(location_planet)が決まっていない")

        planet = planet_of(planet_row)
        neighbors = [self._neighbor(session, origin, place, planet.radius_km)
                     for place in session.scalars(common_query.places_on_planet_select(planet.id)).all()
                     if place.id != origin.id and (self.kind is None or place.kind == self.kind)]
        neighbors.sort(key=lambda neighbor: (neighbor.distance_deg, neighbor.point.id))
        if self.limit is not None:
            neighbors = neighbors[: self.limit]
        return Neighbors(place=map_place_of(session, origin), planet=planet, neighbors=neighbors)

    @staticmethod
    def _neighbor(session, origin: Location, place: Location, radius: float | None) -> Neighbor:
        lon1, lat1 = origin.location_longitude, origin.location_latitude
        lon2, lat2 = place.location_longitude, place.location_latitude
        deg = angular_distance_deg(lon1, lat1, lon2, lat2)
        km = distance_km(radius, lon1, lat1, lon2, lat2)
        bearing = bearing_deg(lon1, lat1, lon2, lat2)
        diff = (float(place.location_altitude) - float(origin.location_altitude)
                if place.location_altitude is not None and origin.location_altitude is not None else None)
        point = map_place_of(session, place)
        direction = "同じ経緯度" if deg < 0.01 else bearing_name(bearing)
        parent = f"・{point.parent_name}" if point.parent_name else ""
        where = "同じ経緯度" if deg < 0.01 else f"{direction} {distance_text(km, deg)}"
        return Neighbor(
            point=point, distance_deg=round(deg, 2), distance_km=None if km is None else round(km),
            bearing_deg=round(bearing), bearing=direction, altitude_diff_m=diff,
            summary=f"{point.name}({point.kind or '種別なし'}{parent}): {where}、{altitude_diff_text(diff)}")
