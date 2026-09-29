from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

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
    sincerity: str | None = None
    curiosity: str | None = None
    proactivity: str | None = None
    cooperativeness: str | None = None
    sociability: str | None = None
    emotional_expression: str | None = None
    self_esteem: str | None = None
    self_efficacy: str | None = None
    stress_resilience: str | None = None
    flexibility_of_values: str | None = None
    sensitivity: str | None = None
    imagination: str | None = None

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
