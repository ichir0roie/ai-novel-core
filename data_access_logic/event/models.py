from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material
from db.stamp import Stamp


class EventSummaryMaterial(Material):
    text: str


class EventBase(Material):
    name: str
    time: Stamp
    start: Stamp | None = None
    end: Stamp | None = None


class EventMaterial(EventBase):
    location: LocationMaterial | None = None
    summary: EventSummaryMaterial | None = None


class EventSerialized(EventMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "名前": self.name,
            "時刻": str(self.start or self.time),
            "終わり": str(self.end) if self.end else None,
            "場所": self.location.name if self.location else None,
            # 本文は写させないよう要約だけを渡す
            "要約": self.summary.text if self.summary else None,
        }


class EventSource(EventBase):
    text: str


class EventSummarySource(EventSource):
    """要約を作り直す出来事。書き戻すときに、要約した本文のハッシュを添える。"""

    id: int
    source_hash: str


class EventSourceSerialized(EventSource):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "名前": self.name,
            "時刻": str(self.start) if self.start else None,
            "終わり": str(self.end) if self.end else None,
            "本文": self.text,
        }


class EventSummaryDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="要約")

    @field_validator("text")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("要約が空")
        return value
