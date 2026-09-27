#!/usr/bin/env python3
from __future__ import annotations

from data_access_logic.query import common_query
from db.schema import Location
from tool.map.category import category_of
from tool.map.geometry import planet_radius_km

__all__ = ["planet_dict", "point_dict", "collect_planets"]


def _num(value):
    return None if value is None else float(value)


def planet_dict(planet) -> dict:
    return {"id": planet.id, "name": planet.name,
            "area": _num(planet.area), "radius_km": planet_radius_km(planet.area)}


def point_dict(session, place) -> dict:
    # `Location.parent` は noload なので、識別マップに先に載った行では None のまま。id で引き直す
    parent = session.get(Location, place.parent_id) if place.parent_id is not None else None
    return {
        "id": place.id, "name": place.name, "kind": place.kind, "category": category_of(place.kind),
        "parent_id": place.parent_id,
        "parent_name": parent.name if parent else None,
        "parent_kind": parent.kind if parent else None,
        "lon": _num(place.location_longitude), "lat": _num(place.location_latitude),
        "alt": _num(place.location_altitude),
        "polygon": place.polygon,
        "environment": place.environment,
        "sample_region": place.sample_region, "sample_culture": place.sample_culture,
        "sample_era": place.sample_era,
        "start": str(place.start) if place.start else None,
        "end": str(place.end) if place.end else None,
        "link": f"/tables/location/{place.id}",
    }


def collect_planets(session) -> list[dict]:
    result = []
    for planet in session.scalars(common_query.planets_select()).all():
        places = session.scalars(common_query.places_on_planet_select(planet.id)).all()
        shapes = session.scalars(common_query.shapes_on_planet_select(planet.id)).all()
        if not places and not shapes:
            continue
        result.append({"planet": planet_dict(planet),
                       "points": [point_dict(session, p) for p in places],
                       "shapes": [point_dict(session, p) for p in shapes]})
    return result
