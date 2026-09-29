from data_access_logic.material import Material, Timestamp


class StoryRecord(Material):
    id: int
    name: str
    world_id: int | None = None
    location_id: int | None = None
    narration: str
    state: str
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool
    parent_story_id: int | None = None
    text: str


class DeletedStory(Material):
    id: int
    name: str
    location_id: int | None = None
    text: str
