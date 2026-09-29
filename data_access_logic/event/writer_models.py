from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic.character.models import ParticipantMaterial, ParticipantSerialized
from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic.location.models import LocationTextMaterial
from data_access_logic.material import Material


class TextlessEvent(EventBase):
    location: LocationTextMaterial | None = None


class EventTextMaterial(Material):
    event: TextlessEvent
    participants: list[ParticipantMaterial]
    later_events: list[EventMaterial]


class EventTextMaterialSerialized(EventTextMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    participants: list[ParticipantSerialized]
    later_events: list[EventSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        event, location = self.event, self.event.location
        return {
            "出来事の名前": event.name,
            "時刻": str(event.start or event.time),
            "終わり": str(event.end) if event.end else None,
            "場所": {"名前": location.name, "種別": location.kind, "説明": location.text} if location else None,
            "当事者": [participant.model_dump() for participant in self.participants],
            "この時点より後に既に決まっている出来事": [later.model_dump() for later in self.later_events],
        }


class EventTextDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="本文")

    @field_validator("text")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("本文が空")
        return value
