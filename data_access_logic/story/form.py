from pydantic import Field

from data_access_logic.material import Form


class StoryCreateForm(Form):
    name: str = Field(min_length=1)
    text: str = ""
    world_id: int | None = None
    location_id: int | None = None
    narration: str = ""
    state: str = ""
    event_seeded: bool = False
    parent_story_id: int | None = None


class StoryUpdateForm(Form):
    id: int
    name: str | None = None
    text: str | None = None
    world_id: int | None = None
    location_id: int | None = None
    narration: str | None = None
    state: str | None = None
    event_seeded: bool | None = None
    parent_story_id: int | None = None
