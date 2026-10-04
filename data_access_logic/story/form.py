from pydantic import Field

from data_access_logic.material import Form


class StoryCreateForm(Form):
    name: str = Field(min_length=1)
    text: str = ""
    parent_story_id: int | None = None
    display_order: int | None = None


class StoryUpdateForm(Form):
    id: int
    name: str | None = None
    text: str | None = None
    parent_story_id: int | None = None
    display_order: int | None = None
