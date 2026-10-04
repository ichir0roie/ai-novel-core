from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from ai.instructions.event_writing import EVENT_DURATION_INSTRUCTION
from data_access_logic import constants
from data_access_logic.character.models import ParticipantMaterial, ParticipantSerialized
from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic.location.models import LocationMaterial, LocationTextMaterial
from data_access_logic.material import Material
from db.stamp import Stamp


class LocationSituationMaterial(Material):
    time: Stamp
    location: LocationTextMaterial
    participants: list[ParticipantMaterial]
    # 新しい順
    recent_events: list[EventBase]
    later_events: list[EventMaterial]
    # ジャンルや場面を一言で決めたもの
    scene: str | None = None


class LocationSituationSerialized(LocationSituationMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    participants: list[ParticipantSerialized]
    later_events: list[EventSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        location = self.location
        return {
            "現在の時刻": str(self.time),
            "場所": {"名前": location.name, "種別": location.kind, "説明": location.text, "環境": location.environment},
            "居合わせる人物・対象": [participant.model_dump() for participant in self.participants],
            "この場所の直近の出来事(新しい順)": [event.name for event in self.recent_events],
            "この時点より後に既に決まっている出来事": [event.model_dump() for event in self.later_events],
            "場面の指定": self.scene,
        }


class CandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="出来事の名前")
    summary: str = Field(description="何が起きて誰が関わるか。2〜3文")

    @field_validator("name", "summary")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


class CandidatesDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateDraft] = Field(description="出来事の候補")

    @field_validator("candidates")
    @classmethod
    def _named(cls, value: list[CandidateDraft]) -> list[CandidateDraft]:
        return [candidate for candidate in value if candidate.name]


class CandidateRequest(Material):
    situation: LocationSituationMaterial
    # この世界のほかの場面の筋から、時代・場所・固有名詞を抜いたもの
    seeds: list[str]


class CandidateRequestSerialized(CandidateRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    situation: LocationSituationSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "場所の状況": self.situation.model_dump(),
            "出来事の種": self.seeds,
        }


class RecordRequest(Material):
    situation: LocationSituationMaterial
    destinations: list[LocationMaterial]
    candidate: CandidateDraft


class RecordRequestSerialized(RecordRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    situation: LocationSituationSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "場所の状況": self.situation.model_dump(),
            "移動先の候補": [
                {"場所id": destination.id, "名前": destination.name, "種別": destination.kind}
                for destination in self.destinations],
            "サイコロで選ばれた出来事の候補": {"名前": self.candidate.name, "概要": self.candidate.summary},
        }


class CharacterMoveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="居場所が変わった人物の人物id")
    location_id: int = Field(description="移動先の候補の場所id")


class CharacterUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="この出来事を通して人となりについて新しく分かった人物・対象の人物id")
    text: str = Field(default="", description="この出来事を通して見えた、その人物の人となり")

    @field_validator("text")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


class FoundedLocationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    text: str
    environment: str


class EventRecordDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(description="出来事の名前")
    event_text: str = Field(description="出来事の内容")
    character_ids: list[int] = Field(description="関わった人物・対象の人物id")
    character_moves: list[CharacterMoveDraft] = Field(description="居場所が変わった人物")
    character_updates: list[CharacterUpdateDraft] = Field(description="この出来事を通して人となりについて新しく分かった人物・対象")
    location_abolished: bool = Field(description="この出来事でこの場所自体が消滅・放棄されたか")
    location_founded: FoundedLocationDraft | None = Field(description="この出来事でこの場所の配下に生まれた新しい場所")
    event_duration_days: int = Field(
        ge=constants.EVENT_DURATION_RANGE_DAYS[0], le=constants.EVENT_DURATION_RANGE_DAYS[1],
        description=EVENT_DURATION_INSTRUCTION)

    @field_validator("event_name")
    @classmethod
    def _named(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("出来事の名前が空")
        return value

    @field_validator("event_duration_days", mode="before")
    @classmethod
    def _clamped(cls, value: Any) -> int:
        try:
            days = int(value)
        except (TypeError, ValueError):
            return constants.DEFAULT_EVENT_DURATION_DAYS
        return min(max(days, constants.EVENT_DURATION_RANGE_DAYS[0]), constants.EVENT_DURATION_RANGE_DAYS[1])
