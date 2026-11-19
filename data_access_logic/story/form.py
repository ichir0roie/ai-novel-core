from typing import Annotated

from pydantic import Field

from data_access_logic.material import Form, References


class StoryCreateForm(Form):
    name: str = Field(min_length=1)
    text: str = ""
    parent_story_id: int | None = None
    custom_stamp_id: Annotated[int | None, References("custom_stamp")] = None
    display_order: int | None = None
    narou_novel_id: int | None = None
    instruction: str = ""


class StoryUpdateForm(Form):
    id: int
    name: str | None = None
    text: str | None = None
    parent_story_id: int | None = None
    custom_stamp_id: Annotated[int | None, References("custom_stamp")] = None
    display_order: int | None = None
    narou_novel_id: int | None = None
    instruction: str | None = None
