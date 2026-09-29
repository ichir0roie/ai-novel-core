from data_access_logic.material import Material, Timestamp


class StoryRecord(Material):
    id: int
    name: str
    world_id: int | None = None
    place_id: int | None = None
    narration: str
    state: str
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool
    text: str


class DeletedStory(Material):
    id: int
    name: str
    place_id: int | None = None
    text: str
