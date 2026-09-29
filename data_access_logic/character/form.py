from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_access_logic.character.record import CharacterHistoryRow, CharacterParameterRow, CharacterPlaceRow
from data_access_logic.material import Form, Timestamp
from db.schema import CHARACTER_KIND_PERSON, ConfirmStatus, PersonalityLevel
from db.stamp import Stamp


def _blank_is_unset(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class CharacterParameterForm(BaseModel):
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

    @field_validator("*", mode="before")
    @classmethod
    def _blank(cls, value: Any) -> Any:
        return _blank_is_unset(value)


class CharacterForm(BaseModel):
    """GUI の欄で渡る、人物の下書き。空の欄は「指定なし」。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int | None = None
    name: str | None = None
    text: str | None = None
    kind: str | None = None
    main_character: bool | None = None
    start: Stamp | None = None
    end: Stamp | None = None
    place_id: int | None = None
    # GUI は期間ごとの行の配列で渡す。生まれるときの値なので先頭の行だけを使う
    parameters: list[CharacterParameterForm] = []

    @field_validator("*", mode="before")
    @classmethod
    def _blank(cls, value: Any) -> Any:
        return _blank_is_unset(value)

    @field_validator("start", "end", mode="before")
    @classmethod
    def _stamp(cls, value: Any) -> Stamp | None:
        return Stamp.parse(value)

    @field_validator("parameters", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        if value is None:
            return []
        return [value] if isinstance(value, dict) else value


class CharacterCreateForm(Form):
    name: str | None = None
    text: str | None = None
    kind: str = CHARACTER_KIND_PERSON
    confirmed: ConfirmStatus = ConfirmStatus.APPROVED
    main_character: bool = False
    event_seeded: bool = False
    meme_seeded: bool = False
    # 出自。`character_place` の行として、誕生から死亡までの期間で足す
    place_id: int | None = None
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
    places: list[CharacterPlaceRow] | None = None
    histories: list[CharacterHistoryRow] | None = None


class CharacterPlaceCreateForm(Form):
    character_id: int
    location_id: int
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterPlaceUpdateForm(Form):
    id: int
    character_id: int | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None


class CharacterRelationCreateForm(Form):
    character_id_1: int
    character_id_2: int
    relation: str = Field(min_length=1)
    text: str = ""
    start: Timestamp | None = None
    end: Timestamp | None = None

    @model_validator(mode="after")
    def _two_characters(self) -> "CharacterRelationCreateForm":
        if self.character_id_1 == self.character_id_2:
            raise ValueError("character_id_1 と character_id_2 は別の人物")
        return self


class CharacterRelationUpdateForm(Form):
    id: int
    character_id_1: int | None = None
    character_id_2: int | None = None
    relation: str | None = None
    text: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
