from pydantic import Field

from data_access_logic.material import Form, Timestamp


class StoryCreateForm(Form):
    name: str = Field(min_length=1)
    text: str = ""
    world_id: int | None = None
    location_id: int | None = None
    narration: str = ""
    state: str = ""
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool = False


class StoryUpdateForm(Form):
    id: int
    name: str | None = None
    text: str | None = None
    world_id: int | None = None
    location_id: int | None = None
    narration: str | None = None
    state: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool | None = None
