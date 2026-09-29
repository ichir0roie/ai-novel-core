from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from ai.instructions.style import layout_novel_text
from data_access_logic.character.models import (
    CastMaterial, CastSerialized, CharacterMaterial, CharacterRelationLine, relations_for_prompt,
)
from data_access_logic.event.models import EventMaterial, EventSerialized
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material
from db.stamp import Stamp


class StoryMaterial(Material):
    name: str
    text: str
    narration: str
    state: str
    start: Stamp | None = None
    end: Stamp | None = None


class EpisodeSummaryMaterial(Material):
    summary: str


class EpisodeBase(Material):
    title: str


class PastEpisode(EpisodeBase):
    start: Stamp | None = None
    summary: EpisodeSummaryMaterial


class RecentEpisode(EpisodeBase):
    start: Stamp | None = None
    text: str


class UnwrittenEpisode(EpisodeBase):
    key: str
    text: str

    @field_validator("text")
    @classmethod
    def _unwritten(cls, value: str) -> str:
        if value.strip():
            raise ValueError("本文の入っている話は書き換えない")
        return value


class TargetEpisode(UnwrittenEpisode):
    start: Stamp
    viewpoint_character: CharacterMaterial | None = None

    @field_validator("key")
    @classmethod
    def _seeded(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("話の種(key)が空")
        return value


class FrameEpisode(UnwrittenEpisode):
    start: Stamp | None = None
    end: Stamp | None = None
    location: LocationMaterial | None = None
    viewpoint_character: CharacterMaterial | None = None


class RevisedEpisode(EpisodeBase):
    start: Stamp
    text: str

    @field_validator("text")
    @classmethod
    def _written(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("本文の無い話は推敲できない(先に本文を書く)")
        return value


def _past_episodes(past_episodes: list[PastEpisode]) -> list[dict[str, Any]]:
    return [
        {"題": past.title, "時刻": str(past.start) if past.start else None, "概要": past.summary.summary}
        for past in past_episodes
    ]


def _recent_episodes(recent_episodes: list[RecentEpisode]) -> list[dict[str, Any]]:
    return [
        {"題": recent.title, "時刻": str(recent.start) if recent.start else None, "本文": recent.text}
        for recent in recent_episodes
    ]


def _location(locations: list[LocationMaterial]) -> str | None:
    return " > ".join(
        f"{location.name}({location.kind})" if location.kind else location.name
        for location in locations if location.name) or None


def _story(story: StoryMaterial) -> dict[str, Any]:
    return {"作品名": story.name, "筋書き": story.text, "語り": story.narration, "状態": story.state}


class EpisodeMaterial(Material):
    story: StoryMaterial
    main_episode: TargetEpisode
    # 直前の話より前の話。古い順
    past_episodes: list[PastEpisode]
    # 直前の話。古い順
    recent_episodes: list[RecentEpisode]
    # 話の場所(無ければ作品の立つ場所)とその親。広い順
    locations: list[LocationMaterial]
    cast: list[CastMaterial]
    # 登場人物のどれかが片側にいる関係
    relations: list[CharacterRelationLine]
    # 古い順
    location_events: list[EventMaterial]
    later_events: list[EventMaterial]
    ideas: IdeaContextMaterial


class EpisodeMaterialSerialized(EpisodeMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    cast: list[CastSerialized]
    location_events: list[EventSerialized]
    later_events: list[EventSerialized]
    ideas: IdeaContextSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "作品": _story(self.story),
            "前の話の概要(古い順)": _past_episodes(self.past_episodes),
            "直前の話の本文(古い順)": _recent_episodes(self.recent_episodes),
            "書く話": {
                "時刻": str(episode.start),
                "場所": _location(self.locations),
                "視点": episode.viewpoint_character.name if episode.viewpoint_character else None,
                "登場人物": [member.model_dump() for member in self.cast],
                "登場人物の関係": relations_for_prompt(self.relations),
                "種": episode.key,
            },
            "この場所の直近の出来事(古い順)": [
                event.model_dump() for event in self.location_events],
            "この時点より後に既に決まっている出来事": [
                event.model_dump() for event in self.later_events],
            "関係する設定": self.ideas.model_dump(),
        }


class EpisodeKeyRequest(Material):
    material: EpisodeMaterial
    # 今の種に加えて、作者が新しい種に望むこと
    order: str | None = None


class EpisodeKeyRequestSerialized(EpisodeKeyRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    material: EpisodeMaterialSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {**self.material.model_dump(), "作者の注文": self.order}


class EpisodeCastingRequest(Material):
    material: EpisodeMaterial
    # 書き直した種。材料の「書く話」の種(書き直す前の種)と置き換わる
    key: str
    # 話の場所の直下にある場所
    known_locations: list[LocationMaterial]


class EpisodeCastingRequestSerialized(EpisodeCastingRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    material: EpisodeMaterialSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            **self.material.model_dump(),
            "新しい種": self.key,
            "この場所の中の既知の場所": [_location([location]) for location in self.known_locations],
        }


class EpisodeRevisionMaterial(Material):
    story: StoryMaterial
    main_episode: RevisedEpisode
    # 直前の話より前の話。古い順
    past_episodes: list[PastEpisode]
    # 直前の話。古い順
    recent_episodes: list[RecentEpisode]
    # 話の場所(無ければ作品の立つ場所)とその親。広い順
    locations: list[LocationMaterial]
    cast: list[CastMaterial]
    # 登場人物のどれかが片側にいる関係
    relations: list[CharacterRelationLine]


class EpisodeRevisionMaterialSerialized(EpisodeRevisionMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    cast: list[CastSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "作品": _story(self.story),
            "前の話の概要(古い順)": _past_episodes(self.past_episodes),
            "直前の話の本文(古い順)": _recent_episodes(self.recent_episodes),
            "直す話": {
                "時刻": str(episode.start),
                "場所": _location(self.locations),
                "登場人物": [member.model_dump() for member in self.cast],
                "登場人物の関係": relations_for_prompt(self.relations),
                "今の題": episode.title,
                "今の本文": episode.text,
            },
        }


class EpisodeFrameMaterial(Material):
    story: StoryMaterial
    main_episode: FrameEpisode
    # 古い順
    past_episodes: list[PastEpisode]
    # 作品の立つ場所とその親。広い順
    locations: list[LocationMaterial]
    cast: list[CastMaterial]
    # 登場人物のどれかが片側にいる関係
    relations: list[CharacterRelationLine]
    later_events: list[EventMaterial]


class EpisodeFrameMaterialSerialized(EpisodeFrameMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    cast: list[CastSerialized]
    later_events: list[EventSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "作品": {
                **_story(self.story),
                "始まり": str(self.story.start) if self.story.start else None,
                "終わり": str(self.story.end) if self.story.end else None,
                "立つ場所": _location(self.locations),
            },
            "前の話の概要(古い順)": _past_episodes(self.past_episodes),
            "登場人物": [member.model_dump() for member in self.cast],
            "登場人物の関係": relations_for_prompt(self.relations),
            "この時点より後に既に決まっている出来事": [
                event.model_dump() for event in self.later_events],
            "作者の指定": {
                "題": episode.title.strip() or None,
                "種": episode.key.strip() or None,
                "時刻": str(episode.start) if episode.start else None,
                "終わり": str(episode.end) if episode.end else None,
                "視点": episode.viewpoint_character.name if episode.viewpoint_character else None,
                "場所": episode.location.name if episode.location else None,
            },
        }


class EpisodeSource(Material):
    title: str
    text: str


class EpisodeSourceSerialized(EpisodeSource):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {"題": self.title, "本文": self.text}


def _laid_out(value: str) -> str:
    text = layout_novel_text(value)
    if not text:
        raise ValueError("本文が空")
    return text


def _not_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("空")
    return value


class EpisodeDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="サブタイトル。短く")
    text: str = Field(description="本文")

    @field_validator("title")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return _laid_out(value)


class EpisodeKeyDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="この話の新しい種。今の種とそっくり置き換わる")

    @field_validator("key")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _not_empty(value)


class EpisodeCharacterCandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    called: str = Field(description="新しい種での呼び名")
    text: str = Field(description="人物像と、この話での役どころ")

    @field_validator("called", "text")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


class EpisodeLocationCandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="名前")
    kind: str = Field(description="種別。店・屋敷・広場など")
    text: str = Field(description="説明")
    environment: str = Field(description="環境")

    @field_validator("name", "kind")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _not_empty(value)


class EpisodeCastingDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    characters: list[EpisodeCharacterCandidateDraft] | None = Field(
        description="新しい種に出てくるのに、登場人物にいない人物。いなければ null")
    location: EpisodeLocationCandidateDraft | None = Field(
        description="新しい種の主な舞台が、書く話の場所より細かく、この場所の中の既知の場所にも無いときの、その舞台。"
                    "それ以外は null")


class EpisodeRevisionDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", description="サブタイトル。直さないなら空")
    text: str = Field(description="書き直した本文")

    @field_validator("title")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return _laid_out(value)


class EpisodeFrameDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="サブタイトル。短く")
    key: str = Field(description="種")
    start: str = Field(description="時刻。「年/月/日」の形")

    @field_validator("title", "start")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _not_empty(value)


class EpisodeSummaryDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="概要")

    @field_validator("summary")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _not_empty(value)
