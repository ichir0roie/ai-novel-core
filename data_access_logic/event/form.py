from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_access_logic.material import Form, Timestamp
from db.schema import ConfirmStatus
from db.stamp import Stamp


class EventForm(BaseModel):
    """GUI の欄で渡る、出来事の下書き。空の欄は「指定なし」。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 渡せば、その出来事の本文だけを埋める(`GenerateEvent`)
    id: int | None = None
    name: str | None = None
    text: str | None = None
    time: Stamp | None = None
    start: Stamp | None = None
    end: Stamp | None = None
    location_id: int | None = None
    character_ids: list[int] | None = None
    hidden: bool = False
    parent_event_id: int | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("time", "start", "end", mode="before")
    @classmethod
    def _stamp(cls, value: Any) -> Stamp | None:
        return Stamp.parse(value)

    @field_validator("hidden", mode="before")
    @classmethod
    def _unset_is_false(cls, value: Any) -> Any:
        return False if value is None else value

    @property
    def scene(self) -> str | None:
        """名前・記録を場面の指定にまとめる。"""
        return " / ".join(part.strip() for part in (self.name, self.text) if part and part.strip()) or None


class EventCreateForm(Form):
    name: str = Field(min_length=1)
    time: Timestamp
    text: str = ""
    hidden: bool = False
    confirmed: ConfirmStatus = ConfirmStatus.APPROVED
    parent_event_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool = False
    meme_seeded: bool = False
    character_ids: list[int] = []


class EventUpdateForm(Form):
    id: int
    name: str | None = None
    time: Timestamp | None = None
    text: str | None = None
    hidden: bool | None = None
    confirmed: ConfirmStatus | None = None
    parent_event_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    event_seeded: bool | None = None
    meme_seeded: bool | None = None
    # 渡すと当事者(`event_character`)をまるごと置き換える
    character_ids: list[int] | None = None
