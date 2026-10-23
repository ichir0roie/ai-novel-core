from data_access_logic.material import Material


class StoryRecord(Material):
    id: int
    name: str
    parent_story_id: int | None = None
    display_order: int | None = None
    narou_novel_id: int | None = None
    text: str
    instruction: str = ""


class DeletedStory(Material):
    id: int
    name: str
    text: str
