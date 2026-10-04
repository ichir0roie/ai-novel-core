from typing import Any, ClassVar

from pydantic import Field, computed_field, model_validator
from sqlalchemy.orm import selectinload

from data_access_logic.character.record import CharacterMove
from data_access_logic.material import Material, Timestamp
from db.schema import Event


class EventColumns(Material):
    id: int
    name: str
    hidden: bool
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

    @model_validator(mode="before")
    @classmethod
    def _from_dumped(cls, value: Any) -> Any:
        # API(`/api/steps`)が JSON にして返した形(`character_ids`)からも読み直せるように
        if isinstance(value, dict) and "event_characters" not in value and "character_ids" in value:
            return {**value, "event_characters": [{"character_id": character_id} for character_id in value["character_ids"]]}
        return value

    @computed_field
    @property
    def character_ids(self) -> list[int]:
        return [link.character_id for link in self.event_characters]


class GeneratedEvent(EventRecord):
    # この出来事で居場所を移した人物の移動先。移していなければ空
    moves: list[CharacterMove] = []


class DeletedEvent(Material):
    id: int
    name: str
