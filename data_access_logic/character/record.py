from pydantic import ConfigDict

from data_access_logic.material import Form, Material, Timestamp
from db.schema import ConfirmStatus, PersonalityLevel


class _ChildRow(Form):
    """人物の子の行(id と character_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CharacterParameterRow(_ChildRow):
    start: Timestamp | None = None
    end: Timestamp | None = None
    family_name: str | None = None
    sex: str | None = None
    height: float | None = None
    build: str | None = None
    first_person: str | None = None
    second_person: str | None = None
    third_person: str | None = None
    tone: str | None = None
    dialect: str | None = None
    sincerity: PersonalityLevel | None = None
    curiosity: PersonalityLevel | None = None
    proactivity: PersonalityLevel | None = None
    cooperativeness: PersonalityLevel | None = None
    sociability: PersonalityLevel | None = None
    emotional_expression: PersonalityLevel | None = None
    self_esteem: PersonalityLevel | None = None
    self_efficacy: PersonalityLevel | None = None
    stress_resilience: PersonalityLevel | None = None
    flexibility_of_values: PersonalityLevel | None = None
    sensitivity: PersonalityLevel | None = None
    imagination: PersonalityLevel | None = None


class CharacterPlaceRow(_ChildRow):
    location_id: int
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterHistoryRow(_ChildRow):
    start: Timestamp | None = None
    end: Timestamp | None = None
    description: str


class CharacterHead(Material):
    id: int
    name: str | None = None
    kind: str
    confirmed: ConfirmStatus
    main_character: bool
    event_seeded: bool
    meme_seeded: bool
    # 誕生・死亡は列を持たず、parameters の行から決まる(`Character.start` / `.end`)
    start: Timestamp | None = None
    end: Timestamp | None = None
    parameters: list[CharacterParameterRow]
    places: list[CharacterPlaceRow]
    histories: list[CharacterHistoryRow]


class CharacterRecord(CharacterHead):
    text: str | None = None


class CharacterPlaceRecord(Material):
    id: int
    character_id: int | None = None
    location_id: int
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterRelationRecord(Material):
    id: int
    character_id_1: int
    character_id_2: int
    relation: str
    start: Timestamp | None = None
    end: Timestamp | None = None
    text: str


class GeneratedCharacter(Material):
    id: int
    name: str | None = None
    place_id: int
