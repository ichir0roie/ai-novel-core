from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from ai.instructions.event_writing import EVENT_DURATION_INSTRUCTION
from data_access_logic import constants
from data_access_logic.character.models import ParticipantCharacter, ParticipantMaterial, ParticipantSerialized
from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic.location.models import LocationMaterial, LocationTextMaterial
from data_access_logic.material import Material
from data_access_logic.story.models import StoryPlotMaterial
from db.stamp import Stamp


class LocationSituationMaterial(Material):
    time: Stamp
    location: LocationTextMaterial
    participants: list[ParticipantMaterial]
    # 新しい順
    recent_events: list[EventBase]
    later_events: list[EventMaterial]
    # 進めたい筋書き。上位の場所のものから順
    stories: list[StoryPlotMaterial]
    # この場所とその上位の場所(作品の立つ場所まで)で直近使われた出来事。新しい順
    story_recent_events: list[EventBase]
    focus_character: ParticipantCharacter | None = None
    focus_previous_event: EventMaterial | None = None
    # ジャンルや場面を一言で決めたもの
    scene: str | None = None


class LocationSituationSerialized(LocationSituationMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    participants: list[ParticipantSerialized]
    later_events: list[EventSerialized]
    focus_previous_event: EventSerialized | None = None

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        location, focus = self.location, self.focus_character
        return {
            "現在の時刻": str(self.time),
            "場所": {"名前": location.name, "種別": location.kind, "説明": location.text},
            "居合わせる人物・対象": [participant.model_dump() for participant in self.participants],
            "この場所の直近の出来事(新しい順)": [event.name for event in self.recent_events],
            "この時点より後に既に決まっている出来事": [event.model_dump() for event in self.later_events],
            "進めたい筋書き": "\n\n".join(story.text for story in self.stories if story.text) or None,
            "筋書きに関わる直近の出来事(新しい順)": [event.name for event in self.story_recent_events],
            "主役": {"人物id": focus.id, "名前": focus.name} if focus else None,
            "主役の直前の出来事": self.focus_previous_event.model_dump() if self.focus_previous_event else None,
            "場面の指定": self.scene,
        }


class JudgementDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    thought: str = Field(description="思考。いまの状況をどう受け止め、何を考えているか。1〜2文")
    emotion: str = Field(description="感情。何に対して怒り・喜び・悲しみ・退屈・不安などを抱いているか。感情の名前を含める。1〜2文")
    wish: str = Field(description="望み。何を手に入れたい・何をしたいか。1〜2文")
    fear: str = Field(description="恐れ。何を失いたくない・何が起きてほしくないか。1〜2文")
    action: str = Field(description="行動。この時点で実際に何をするか。話す・動く・作る・出かける・黙るなど具体的な動作で。1〜2文")

    @field_validator("thought", "emotion", "wish", "fear")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("action")
    @classmethod
    def _acted(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("行動が空")
        return value


class ParticipantJudgement(Material):
    character: ParticipantCharacter
    judgement: JudgementDraft


def _judgements(judgements: list[ParticipantJudgement]) -> list[dict[str, Any]]:
    return [
        {
            "人物id": judged.character.id,
            "名前": judged.character.name,
            "思考": judged.judgement.thought,
            "感情": judged.judgement.emotion,
            "望み": judged.judgement.wish,
            "恐れ": judged.judgement.fear,
            "行動": judged.judgement.action,
        }
        for judged in judgements
    ]


class JudgementRequest(Material):
    situation: LocationSituationMaterial
    participant: ParticipantMaterial


class JudgementRequestSerialized(JudgementRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    situation: LocationSituationSerialized
    participant: ParticipantSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "場所の状況": self.situation.model_dump(),
            "この当事者": self.participant.model_dump(),
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
    judgements: list[ParticipantJudgement]
    # 時代・場所を抜いた、別の物語から取ったアイデア
    seeds: list[str]


class CandidateRequestSerialized(CandidateRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    situation: LocationSituationSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "場所の状況": self.situation.model_dump(),
            "当事者ごとの思考・感情・望み・恐れ・行動": _judgements(self.judgements),
            "出来事の種": self.seeds,
        }


class RecordRequest(Material):
    situation: LocationSituationMaterial
    judgements: list[ParticipantJudgement]
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
            "当事者ごとの思考・感情・望み・恐れ・行動": _judgements(self.judgements),
            "サイコロで選ばれた出来事の候補": {"名前": self.candidate.name, "概要": self.candidate.summary},
        }


class CharacterMoveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="居場所が変わった人物の人物id")
    location_id: int = Field(description="移動先の候補の場所id")


class CharacterUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="レコード自体が変わった人物・対象の人物id")
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
    character_updates: list[CharacterUpdateDraft] = Field(description="この出来事でレコード自体が変わった人物・対象")
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
