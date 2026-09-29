from pydantic import Field, computed_field

from data_access_logic.material import Material, Timestamp


class EpisodeHead(Material):
    id: int
    story_id: int
    title: str
    synced: bool
    start: Timestamp | None = None
    end: Timestamp | None = None
    viewpoint_character_id: int | None = None
    place_id: int | None = None
    letters: int
    key: str
    event_seeded: bool


class EpisodeRow(EpisodeHead):
    text: str


class EpisodeCharacterLink(Material):
    character_id: int


class EpisodeRecord(EpisodeRow):
    episode_characters: list[EpisodeCharacterLink] = Field(exclude=True)

    @computed_field
    @property
    def character_ids(self) -> list[int]:
        return [link.character_id for link in self.episode_characters]
