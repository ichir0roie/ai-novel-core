from data_access_logic.material import Material


class StoryRecord(Material):
    id: int
    name: str
    world_id: int | None = None
    location_id: int | None = None
    narration: str
    state: str
    event_seeded: bool
    parent_story_id: int | None = None
    text: str


class DeletedStory(Material):
    id: int
    name: str
    location_id: int | None = None
    text: str
