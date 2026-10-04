#!/usr/bin/env python3
"""作品の話が場所をどう移るか。GUI の地図(`/maps?story=`)が話の順に場所を結んで描く。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from db.polygon import polygon_center
from db.schema import Episode, Location, Story


class RouteStop(BaseModel):
    episode_id: int
    title: str
    start: str | None
    story_id: int
    location_id: int | None
    location_name: str | None
    # 地図に置いた場所。話の場所が経緯度も輪郭も持たなければ、持っている一番近い上位の場所
    placed_id: int | None
    placed_name: str | None
    planet_id: int | None
    lon: float | None
    lat: float | None


class StoryRoute(BaseModel):
    story_id: int
    story_name: str
    # 作品と子孫の作品(章・外伝)の話を、作品の中の並び(時刻の順、時刻の無い話は後ろに id 順)で
    stops: list[RouteStop]


def _position(location: Location) -> tuple[float, float] | None:
    if location.location_longitude is not None and location.location_latitude is not None:
        return float(location.location_longitude), float(location.location_latitude)
    if location.polygon is not None:
        return polygon_center(location.polygon)
    return None


def _placed(location: Location, locations: dict[int, Location]) -> Location | None:
    current: Location | None = location
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        if current.location_planet is not None and _position(current) is not None:
            return current
        seen.add(current.id)
        current = locations.get(current.parent_id) if current.parent_id is not None else None
    return None


def story_route(s: Session, story_id: int) -> StoryRoute:
    story = common_query.get_row(s, Story, story_id)
    episodes = s.scalars(
        select(Episode)
        .where(Episode.story_id.in_(common_query.descendant_story_ids(s, story_id)))
        .order_by(Episode.start.asc().nulls_last(), Episode.id.asc())).all()
    # 上位の場所をたどるので、場所は一度に全部引く
    locations = {location.id: location for location in s.scalars(select(Location))}
    stops = []
    for episode in episodes:
        location = locations.get(episode.location_id) if episode.location_id is not None else None
        placed = _placed(location, locations) if location is not None else None
        position = _position(placed) if placed is not None else None
        stops.append(RouteStop(
            episode_id=episode.id, title=episode.title,
            start=str(episode.start) if episode.start else None, story_id=episode.story_id,
            location_id=episode.location_id, location_name=location.name if location else None,
            placed_id=placed.id if placed else None, placed_name=placed.name if placed else None,
            planet_id=placed.location_planet if placed else None,
            lon=position[0] if position else None, lat=position[1] if position else None))
    return StoryRoute(story_id=story.id, story_name=story.name, stops=stops)
