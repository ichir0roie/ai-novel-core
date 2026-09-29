from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from db.stamp import Stamp


class EventForm(BaseModel):
    """GUI の欄で渡る、出来事の下書き。空の欄は「指定なし」。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

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
