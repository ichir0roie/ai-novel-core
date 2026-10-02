from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from data_access_logic.character.record import CharacterHistoryRow, CharacterParameterRow, CharacterLocationRow
from data_access_logic.material import Draft, Form, References, Timestamp
from db.schema import CHARACTER_KIND_PERSON, ConfirmStatus, PersonalityLevel


class CharacterParameterForm(Draft):
    """作者が決めた性別・体格・口調・性格など。空の欄はサイコロ(性格)か AI が決める。"""

    family_name: str | None = None
    sex: str | None = None
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


class CharacterForm(Draft):
    """人物の下書き。"""

    id: int | None = None
    name: str | None = None
    # 人物像・役どころの下書き。核として AI に渡す
    text: str | None = None
    kind: str | None = None
    main_character: bool | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    location_id: int | None = None
    # GUI は期間ごとの行の配列で渡す。生まれるときの値なので先頭の行だけを使う
    parameters: list[CharacterParameterForm] = []
    # 来歴の下書き。行の説明も核として AI に渡す(年は見ない)
    histories: list[CharacterHistoryRow] = []

    @field_validator("parameters", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        return [value] if isinstance(value, dict) else value


class CharacterCreateForm(Form):
    name: str | None = None
    text: str | None = None
    kind: str = CHARACTER_KIND_PERSON
    confirmed: ConfirmStatus = ConfirmStatus.APPROVED
    main_character: bool = False
    event_seeded: bool = False
    meme_seeded: bool = False
    # `character_location` の行として、誕生から死亡までの期間で足す
    location_id: Annotated[int | None, References("location")] = Field(
        default=None, title="出自(場所)", description="足すときの出自。CharacterLocation の一番古い行になる")
    start: Timestamp | None = None
    end: Timestamp | None = None
    parameters: list[CharacterParameterRow] = []
    histories: list[CharacterHistoryRow] = []


class CharacterUpdateForm(Form):
    id: int
    name: str | None = None
    text: str | None = None
    kind: str | None = None
    confirmed: ConfirmStatus | None = None
    main_character: bool | None = None
    event_seeded: bool | None = None
    meme_seeded: bool | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    # 渡すと配列をまるごと置き換える
    parameters: list[CharacterParameterRow] | None = None
    locations: list[CharacterLocationRow] | None = None
    histories: list[CharacterHistoryRow] | None = None


class CharacterLocationCreateForm(Form):
    character_id: int
    location_id: int
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterLocationUpdateForm(Form):
    id: int
    character_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterRelationCreateForm(Form):
    character_1_id: int
    character_2_id: int
    relation: str = Field(min_length=1)
    text: str = ""
    start: Timestamp | None = None
    end: Timestamp | None = None

    @model_validator(mode="after")
    def _two_characters(self) -> "CharacterRelationCreateForm":
        if self.character_1_id == self.character_2_id:
            raise ValueError("character_1_id と character_2_id は別の人物")
        return self


class CharacterRelationUpdateForm(Form):
    id: int
    character_1_id: int | None = None
    character_2_id: int | None = None
    relation: str | None = None
    text: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
