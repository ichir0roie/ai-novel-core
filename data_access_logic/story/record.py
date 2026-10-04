from data_access_logic.material import Material


class StoryRecord(Material):
    id: int
    name: str
    parent_story_id: int | None = None
    text: str


class DeletedStory(Material):
    id: int
    name: str
    text: str
