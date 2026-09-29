from typing import ClassVar

from pydantic import Field, computed_field
from sqlalchemy.orm import selectinload

from data_access_logic.material import Material, Timestamp
from db.schema import ConfirmStatus, Event


class EventColumns(Material):
    id: int
    name: str
    hidden: bool
    confirmed: ConfirmStatus
    time: Timestamp
    parent_event_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool
    meme_seeded: bool


class EventCharacterLink(Material):
    character_id: int


class EventRecord(EventColumns):
    LOAD_OPTIONS: ClassVar[tuple] = (selectinload(Event.event_characters),)

    text: str
    event_characters: list[EventCharacterLink] = Field(exclude=True)

    @computed_field
    @property
    def character_ids(self) -> list[int]:
        return [link.character_id for link in self.event_characters]


class DeletedEvent(Material):
    id: int
    name: str
