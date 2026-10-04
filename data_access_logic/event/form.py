from typing import Annotated

from pydantic import Field

from data_access_logic.material import Draft, Form, References, Timestamp


class EventForm(Draft):
    """出来事の下書き。"""

    # 渡せば、その出来事の本文だけを埋める(`GenerateEvent`)
    id: int | None = None
    name: str | None = None
    text: str | None = None
    time: Timestamp | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    location_id: int | None = None
    character_ids: list[int] | None = None
    hidden: bool = False
    parent_event_id: int | None = None

    @property
    def scene(self) -> str | None:
        """名前・記録を場面の指定にまとめる。"""
        return " / ".join(part.strip() for part in (self.name, self.text) if part and part.strip()) or None


class EventCreateForm(Form):
    name: str = Field(min_length=1)
    time: Timestamp
    text: str = ""
    hidden: bool = False
    parent_event_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool = False
    meme_seeded: bool = False
    character_ids: Annotated[list[int], References("character")] = Field(
        default=[], description="居合わせた人物の id")


class EventUpdateForm(Form):
    id: int
    name: str | None = None
    time: Timestamp | None = None
    text: str | None = None
    hidden: bool | None = None
    parent_event_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool | None = None
    meme_seeded: bool | None = None
    # 渡すと当事者(`event_character`)をまるごと置き換える
    character_ids: list[int] | None = None
