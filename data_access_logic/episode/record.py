from typing import Any, ClassVar

from pydantic import Field, computed_field, model_validator
from sqlalchemy.orm import selectinload

from data_access_logic.material import Material, Timestamp
from db.schema import Episode


class EpisodeHead(Material):
    id: int
    story_id: int
    title: str
    synced: bool
    start: Timestamp | None = None
    end: Timestamp | None = None
    viewpoint_character_id: int | None = None
    location_id: int | None = None
    letters: int
    plot_text: str
    event_seeded: bool


class EpisodeRow(EpisodeHead):
    main_text: str


class EpisodeCharacterLink(Material):
    character_id: int
    mentioned: bool = False


class EpisodeRecord(EpisodeRow):
    LOAD_OPTIONS: ClassVar[tuple] = (selectinload(Episode.episode_characters),)

    episode_characters: list[EpisodeCharacterLink] = Field(exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _from_dumped(cls, value: Any) -> Any:
        # API(`/api/steps`)が JSON にして返した形(`character_ids`)からも読み直せるように
        if isinstance(value, dict) and "episode_characters" not in value and "character_ids" in value:
            return {**value, "episode_characters": [
                *({"character_id": character_id} for character_id in value["character_ids"]),
                *({"character_id": character_id, "mentioned": True}
                  for character_id in value.get("mentioned_character_ids", [])),
            ]}
        return value

    @computed_field
    @property
    def character_ids(self) -> list[int]:
        return [link.character_id for link in self.episode_characters if not link.mentioned]

    @computed_field(description="この話に登場せず、プロット・本文に名前が出るだけの人物")
    @property
    def mentioned_character_ids(self) -> list[int]:
        return [link.character_id for link in self.episode_characters if link.mentioned]


class EpisodeSummaryRecord(Material):
    id: int
    summary_text: str
