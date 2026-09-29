from data_access_logic.query.base import *


def load_location_story(s: Session, location_id: int, time: Stamp):
    location = s.get(Location, location_id)
    if location is None:
        raise ValueError()

    location_ids = [location.id]
    while location.parent_id is not None:
        location = s.get(Location, location.parent_id)
        if location is None:
            break
        location_ids.append(location.id)

    depth = {lid: i for i, lid in enumerate(reversed(location_ids))}
    stories = s.scalars(
        select(Story).where(
            Story.place_id.in_(location_ids),
            story_time_condition(time),
        ).order_by(Story.id)
    ).all()
    return sorted(stories, key=lambda story: depth[story.place_id])
