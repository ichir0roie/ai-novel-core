from pydantic import ConfigDict

from data_access_logic.material import Form, Material, Timestamp
from db.schema import ConfirmStatus, PersonalityLevel


class _ChildRow(Form):
    """人物の子の行(id と character_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CharacterParameterRow(_ChildRow):
    start: Timestamp | None = None
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


class CharacterLocationRow(_ChildRow):
    location_id: int
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterHistoryRow(_ChildRow):
    # 年。同じ年のことは一行にまとめる
    start: int | None = None
    description: str


class CharacterHead(Material):
    id: int
    name: str | None = None
    kind: str
    confirmed: ConfirmStatus
    main_character: bool
    event_seeded: bool
    meme_seeded: bool
    # 誕生は列を持たず、parameters の一番早く始まる行の start(`Character.start`)
    start: Timestamp | None = None
    # 没年
    end: Timestamp | None = None
    parameters: list[CharacterParameterRow]
    locations: list[CharacterLocationRow]


class CharacterRecord(CharacterHead):
    # すべての行。話・出来事に渡すときは、その時刻に掛かる行だけに絞る(`histories_at`)
    histories: list[CharacterHistoryRow]


class CharacterLocationRecord(Material):
    id: int
    character_id: int | None = None
    location_id: int
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterRelationRecord(Material):
    id: int
    character_1_id: int
    character_2_id: int
    relation: str
    start: Timestamp | None = None
    end: Timestamp | None = None
    text: str


class GeneratedCharacter(Material):
    id: int
    name: str | None = None
    location_id: int
