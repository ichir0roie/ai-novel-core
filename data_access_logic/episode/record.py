from typing import ClassVar

from pydantic import Field, computed_field
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


class EpisodeRecord(EpisodeRow):
    LOAD_OPTIONS: ClassVar[tuple] = (selectinload(Episode.episode_characters),)

    episode_characters: list[EpisodeCharacterLink] = Field(exclude=True)

    @computed_field
    @property
    def character_ids(self) -> list[int]:
        return [link.character_id for link in self.episode_characters]


class EpisodeSummaryRecord(Material):
    id: int
    summary_text: str
