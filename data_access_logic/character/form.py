from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from data_access_logic.character.record import (
    CharacterHistoryRow, CharacterLocationRow, CharacterParameterRow, CharacterRelationHistoryRow,
    CharacterSkillHistoryRow,
)
from data_access_logic.material import Draft, Form, References, Timestamp
from db.schema import CHARACTER_KIND_PERSON, PersonalityLevel


class CharacterParameterForm(Draft):
    """作者が決めた性別・体格・口調・性格など。空の欄は、人物の生成で AI がミームと人物像から決める。"""

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
    appearance: str | None = None
    meme: str | None = None
    principle: str | None = None
    plot: str | None = None
    kind: str = CHARACTER_KIND_PERSON
    main_character: bool = False
    event_seeded: bool = False
    # `character_location` の行として、誕生から死亡までの期間で足す
    location_id: Annotated[int | None, References("location")] = Field(
        default=None, description="足すときの出自。CharacterLocation の一番古い行になる")
    start: Timestamp | None = None
    end: Timestamp | None = None
    parameters: list[CharacterParameterRow] = []
    histories: list[CharacterHistoryRow] = []


class CharacterUpdateForm(Form):
    id: int
    name: str | None = None
    text: str | None = None
    appearance: str | None = None
    meme: str | None = None
    principle: str | None = None
    plot: str | None = None
    kind: str | None = None
    main_character: bool | None = None
    event_seeded: bool | None = None
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
    # 関係の来歴(起きた年ごとの行)
    histories: list[CharacterRelationHistoryRow] = []

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
    # 渡せば来歴の行をまるごと置き換える
    histories: list[CharacterRelationHistoryRow] | None = None


class CharacterSkillCreateForm(Form):
    character_id: int
    name: str = Field(min_length=1)
    # スキルの本質(何ができるか・仕組み・限界)。作者だけが読む
    text: str = ""
    # スキルの来歴(起きた年ごとの行)
    histories: list[CharacterSkillHistoryRow] = []


class CharacterSkillUpdateForm(Form):
    id: int
    character_id: int | None = None
    name: str | None = Field(default=None, min_length=1)
    text: str | None = None
    # 渡せば来歴の行をまるごと置き換える
    histories: list[CharacterSkillHistoryRow] | None = None


class KnowledgeChange(Form):
    # 知られる来歴・履歴の行の id
    id: int
    # true なら知る相手に入れ(入っていれば知った時刻を直す)、false なら外す
    known: bool
    # 知った時刻。空なら、知る人物の生まれ(場所なら、知られる行の始まりか場所のできた時刻)が入る。known が false なら使わない
    start: Timestamp | None = None


class KnowledgeForm(Form):
    """人物が知るもの(人物の来歴・スキルの来歴・アイデアの履歴・場所の来歴)の知る相手の付け外しを、まとめて渡す(GUI の知識整理)。"""

    knower_id: Annotated[int, References("character")]
    character_histories: list[KnowledgeChange] = []
    character_skill_histories: list[KnowledgeChange] = []
    idea_histories: list[KnowledgeChange] = []
    location_histories: list[KnowledgeChange] = []
