from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from data_access_logic.query import common_query
from db.schema import Episode, Location, Story


def load_location_story(s: Session, location_id: int) -> list[Story]:
    """その場所と上位の場所に話を置く作品を、上位の場所の話を持つものから順に。"""
    common_query.get_row(s, Location, location_id)
    location_ids = [step.id for step in common_query.location_path(s, location_id)]
    depth = {id_: index for index, id_ in enumerate(location_ids)}
    episodes = s.scalars(select(Episode).options(load_only(Episode.story_id, Episode.location_id))
                         .where(Episode.location_id.in_(location_ids))).all()
    story_depth: dict[int, int] = {}
    for episode in episodes:
        story_depth[episode.story_id] = min(story_depth.get(episode.story_id, len(depth)), depth[episode.location_id])
    stories = s.scalars(select(Story).where(Story.id.in_(story_depth)).order_by(Story.id)).all()
    return sorted(stories, key=lambda story: story_depth[story.id])
