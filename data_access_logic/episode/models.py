from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from ai.instructions.style import layout_novel_text
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material
from db.schema import ConfirmStatus
from db.stamp import Stamp


class StoryMaterial(Material):
    name: str
    text: str
    narration: str


class CharacterMaterial(Material):
    name: str
    text: str | None = None
    confirmed: ConfirmStatus

    @field_validator("confirmed")
    @classmethod
    def _approved_only(cls, value: ConfirmStatus) -> ConfirmStatus:
        if value != ConfirmStatus.APPROVED:
            raise ValueError("ユーザが承認していない人物は話に出せない")
        return value


class EpisodeCharacterMaterial(Material):
    character: CharacterMaterial


class EpisodeSummaryMaterial(Material):
    summary: str
    style: str


class EpisodeBase(Material):
    title: str
    start: Stamp


class PastEpisode(EpisodeBase):
    summary: EpisodeSummaryMaterial


class TargetEpisode(EpisodeBase):
    key: str
    place: LocationMaterial | None = None
    viewpoint_character: CharacterMaterial | None = None
    episode_characters: list[EpisodeCharacterMaterial]


class EpisodeMaterial(Material):
    story: StoryMaterial
    main_episode: TargetEpisode
    past_episodes: list[PastEpisode]
    # 話の場所とその親。広い順
    locations: list[LocationMaterial]
    ideas: IdeaContextMaterial


class EpisodeMaterialSerialized(EpisodeMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        episode = self.main_episode
        latest = self.past_episodes[0] if self.past_episodes else None
        return {
            "作品": {
                "作品名": self.story.name,
                "筋書き": self.story.text,
                "語り": self.story.narration,
            },
            "直前の話(新しい順)": [
                {"題": past.title, "時刻": str(past.start), "概要": past.summary.summary}
                for past in self.past_episodes
            ],
            "揃える文体": latest.summary.style if latest else None,
            "書く話": {
                "時刻": str(episode.start),
                "場所": " > ".join(
                    f"{location.name}({location.kind})" if location.kind else location.name
                    for location in self.locations) or None,
                "視点": episode.viewpoint_character.name if episode.viewpoint_character else None,
                "登場人物": [
                    {"名前": link.character.name, "人物像": link.character.text}
                    for link in episode.episode_characters
                ],
                "種": episode.key.strip(),
            },
            "関係する設定": IdeaContextSerialized.model_validate(self.ideas).model_dump(),
        }


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
    def _laid_out(cls, value: str) -> str:
        text = layout_novel_text(value)
        if not text:
            raise ValueError("本文が空")
        return text
