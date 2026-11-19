from data_access_logic.material import Material
from db.stamp import Calendar
from db.story_scope import Scope


class StoryRecord(Material):
    id: int
    origin: str = "user"
    name: str
    parent_story_id: int | None = None
    custom_stamp_id: int | None = None
    display_order: int | None = None
    narou_novel_id: int | None = None
    text: str
    instruction: str = ""


class PlacedRows(Material):
    story_id: int
    table: str
    ids: list[int]


class ScopeRecord(Material):
    story_id: int | None = None
    custom_stamp_id: int | None = None
    # `db/stamp.py` の `Calendar.to_json`。空なら西暦
    calendar: dict | None = None

    @classmethod
    def of(cls, scope: Scope) -> "ScopeRecord":
        return cls(story_id=scope.story_id, custom_stamp_id=scope.custom_stamp_id,
                   calendar=None if scope.calendar is None else scope.calendar.to_json())

    def scope(self) -> Scope:
        return Scope(story_id=self.story_id, custom_stamp_id=self.custom_stamp_id,
                     calendar=None if self.calendar is None else Calendar.from_json(self.calendar))


class DeletedStory(Material):
    id: int
    name: str
    text: str
