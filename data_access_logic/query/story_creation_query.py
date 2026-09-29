from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import Location, Story
from db.stamp import Stamp


def load_location_story(s: Session, location_id: int, time: Stamp) -> list[Story]:
    """その場所と上位の場所に掛かる作品を、上位の場所のものから順に。"""
    common_query.get_row(s, Location, location_id)
    location_ids = [step.id for step in common_query.location_path(s, location_id)]
    depth = {id_: index for index, id_ in enumerate(location_ids)}
    stories = s.scalars(
        select(Story).where(Story.location_id.in_(location_ids), alive_at(Story, time)).order_by(Story.id)
    ).all()
    return sorted(stories, key=lambda story: depth[story.location_id])
