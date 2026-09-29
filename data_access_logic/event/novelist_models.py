from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from ai.instructions.style import layout_novel_text
from data_access_logic.character.models import CharacterBase, EventCharacterAt, EventCharacterAtSerialized
from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized
from data_access_logic.location.models import PlaceMaterial
from data_access_logic.material import Material


class RecordedEvent(EventBase):
    text: str
    location: PlaceMaterial | None = None


class EventNovelMaterial(Material):
    main_event: RecordedEvent
    # 視点人物。無ければ AI が当事者から選ぶ
    focus_character: CharacterBase | None = None
    # ジャンルや場面を一言で決めたもの
    scene: str | None = None
    event_characters: list[EventCharacterAt]
    later_events: list[EventMaterial]
    ideas: IdeaContextMaterial


class EventNovelMaterialSerialized(EventNovelMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    event_characters: list[EventCharacterAtSerialized]
    later_events: list[EventSerialized]
    ideas: IdeaContextSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        event, place = self.main_event, self.main_event.location
        return {
            "場所": {"名前": place.name, "種別": place.kind, "説明": place.text} if place else None,
            "時刻": str(event.start or event.time),
            "終わり": str(event.end) if event.end else None,
            "場面の指定": self.scene,
            "主役": self.focus_character.name if self.focus_character else None,
            "当事者": [at.model_dump() for at in self.event_characters],
            "この時点より後に既に決まっている出来事": [
                later.model_dump() for later in self.later_events],
            "この出来事の記録": {"名前": event.name, "記録": event.text},
            "関係する設定": self.ideas.model_dump(),
        }


class EventNovelDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="本文")

    @field_validator("text")
    @classmethod
    def _laid_out(cls, value: str) -> str:
        text = layout_novel_text(value)
        if not text:
            raise ValueError("本文が空")
        return text
