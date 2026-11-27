from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.models import ParticipantMaterial, ParticipantSerialized
from data_access_logic.character.record import CharacterMove
from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic.history_start import start_for_prompt
from data_access_logic.location.models import LocationLine, LocationMaterial
from data_access_logic.material import Material
from db.schema import NuanceKind
from db.stamp import Stamp

# 出力の型の欄の説明(JSON Schema)に入るので、db の指示の行でなくここに置く
_SHORTEST_DAYS, _LONGEST_DAYS = constants.EVENT_DURATION_RANGE_DAYS
EVENT_DURATION_INSTRUCTION = f"この出来事の影響が続く日数の整数。{_SHORTEST_DAYS}〜{_LONGEST_DAYS}"

# 出来事の記録と人物モードの一日の記録が、同じ欄(`nuance_changes`)を書く
NUANCE_CHANGES_NOTE = """\
nuance_changes は、この記録で新しく見えた、その人物らしい癖(決まった場面でする振る舞い)か思い込み(人や世の中をまずこう受け取る)。
その日にしたことそのものと、誰でもする当たり前の振る舞いは書かない。「癖と思い込み」に今ある中身なら書かず、変わったならその id を replaces_nuance_id に書く。
癖は場面を必ず書き、その相手との場面でだけ出るなら相手の人物idを書く。その人物の振る舞いとして主語を書かずに書き、ほかの人物は名前で書く。"""


class LocationSituationMaterial(Material):
    time: Stamp
    # 来歴は時刻の年まで
    location: LocationLine
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
            "場所": {"名前": location.name, "種別": location.kind, "説明": location.text, "環境": location.environment,
                   "来歴(古い順)": [f"{start_for_prompt(history.start)}: {history.description}" for history in location.histories]},
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


class NuanceChangeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="癖・思い込みが新しく見えた・変わった人物・対象の人物id")
    kind: NuanceKind = Field(description="「癖」(決まった場面でする振る舞い)か「思い込み」(人や世の中をまずこう受け取る)")
    situation: str = Field(default="", description="癖の出る場面。思い込みは空")
    target_character_id: int | None = Field(
        default=None, description="癖がその相手との場面でだけ出るなら、相手の人物id。相手を限らない癖と思い込みは null")
    text: str = Field(description="癖ならその場面でする振る舞い、思い込みならその中身。一文")
    replaces_nuance_id: int | None = Field(
        default=None, description="今ある癖・思い込みが変わったなら、その癖・思い込みid。新しく見えたなら null")

    @field_validator("situation", "text")
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
    character_moves: list[CharacterMove] = Field(description="住まい・拠点が変わった人物ごとの移動先。誰も変わっていなければ空")
    nuance_changes: list[NuanceChangeDraft] = Field(
        description="この出来事で新しく見えた・変わった、人物・対象の癖と思い込み。無ければ空")
    location_abolished: bool = Field(description="この出来事でこの場所自体が消滅・放棄されたか")
    location_founded: FoundedLocationDraft | None = Field(description="この出来事でこの場所の配下に生まれた新しい場所")
    event_duration_days: int = Field(ge=_SHORTEST_DAYS, le=_LONGEST_DAYS, description=EVENT_DURATION_INSTRUCTION)

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
        return min(max(days, _SHORTEST_DAYS), _LONGEST_DAYS)
