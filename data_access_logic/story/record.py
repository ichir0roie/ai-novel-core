from data_access_logic.material import Dated, Material


class StoryRecord(Dated):
    id: int
    name: str
    parent_story_id: int | None = None
    display_order: int | None = None
    text: str


class DeletedStory(Material):
    id: int
    name: str
    text: str
