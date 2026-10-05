from pydantic import BaseModel, ConfigDict, Field

from data_access_logic.knowers import KnowerRow
from data_access_logic.material import Form, Material, Timestamp
from db.schema import PersonalityLevel


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
    # 起きた年。同じ年のことは一行にまとめる。空なら年が決まっていない(話・出来事には渡さない)
    start: int | None = None
    description: str
    # 知る相手。この相手だけが来歴を知る(本人も、入れなければ知らない)。渡さなければ、新しい行は本人だけ、
    # 今ある行はそのまま(`db/child_lists.py` の `replaced_histories`)
    knowers: list[KnowerRow] | None = None


class CharacterSkillHistoryRow(_ChildRow):
    # 起きた年。同じ年のことは一行にまとめる。空なら年が決まっていない(話・人物役には渡さない)
    start: int | None = None
    description: str
    # 知る相手。この相手だけが来歴を知る(本人も、入れなければ知らない)。渡さなければ、新しい行はスキルを持つ本人だけ、
    # 今ある行はそのまま(`db/child_lists.py` の `replaced_histories`)
    knowers: list[KnowerRow] | None = None


class CharacterRelationHistoryRow(_ChildRow):
    # 起きた年。同じ年のことは一行にまとめる。空なら年が決まっていない(話・人物役には渡さない)
    start: int | None = None
    description: str


class CharacterHead(Material):
    id: int
    name: str | None = None
    kind: str
    main_character: bool
    event_seeded: bool
    # 誕生は列を持たず、parameters の一番早く始まる行の start(`Character.start`)
    start: Timestamp | None = None
    # 没年
    end: Timestamp | None = None
    parameters: list[CharacterParameterRow]
    locations: list[CharacterLocationRow]


class CharacterRecord(CharacterHead):
    appearance: str | None = None
    # 人物の芯(経歴・立場・性格の説明)
    text: str | None = None
    meme: str | None = None
    principle: str | None = None
    plot: str | None = None
    # すべての来歴の行。話・出来事に渡すときは、その時刻までに起きた行だけに絞る(`histories_at`)
    histories: list[CharacterHistoryRow]
    # 本文(`text`)を知る相手
    knowers: list[KnowerRow]


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
    # 関係の芯(時期を限らない)
    text: str
    # すべての来歴の行。話・人物役に渡すときは、その時刻までに起きた行だけに絞る(`cast.relations_at`)
    histories: list[CharacterRelationHistoryRow]


class CharacterSkillRecord(Material):
    id: int
    character_id: int
    name: str
    # すべての来歴の行。話・人物役に渡すときは、その時刻までに起きた行だけに絞る(`skills.skills_at`)
    histories: list[CharacterSkillHistoryRow]
    # スキルの本質。作者だけが読む
    text: str


class CharacterSkillName(Material):
    id: int
    character_id: int
    name: str


class GeneratedCharacter(Material):
    id: int
    name: str | None = None
    location_id: int


# 人物の居場所の移動。出来事・話の AI の応答と、居場所を書き換える入口(`MoveCharacters`)・レスポンスで使う
# (json schema として AI に渡すので、docstring を書くと description として AI に渡る)
class CharacterMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="住まい・拠点が変わった人物の人物id")
    location_id: int = Field(description="移動先の場所id")



class CharacterTextEntry(Material):
    """知る相手を直すために読む、人物の芯(`text`)とその知る相手(`ReadKnowableRows`)。"""

    id: int
    name: str | None = None
    text: str | None = None
    knowers: list[KnowerRow]


class CharacterHistoryEntry(Material):
    """知る相手を直すために、行を id で指せる人物の来歴の行(`ReadKnowableRows`)。"""

    id: int
    character_id: int
    start: int | None = None
    description: str
    knowers: list[KnowerRow]


class CharacterSkillHistoryEntry(Material):
    """知る相手を直すために、行を id で指せるスキルの来歴の行(`ReadKnowableRows`)。"""

    id: int
    character_skill_id: int
    start: int | None = None
    description: str
    knowers: list[KnowerRow]


class CharacterSkillEntry(Material):
    """知る相手を直すために読む、スキルとその来歴の行(`ReadKnowableRows`)。スキルの本文は作者だけが読むので持たない。"""

    id: int
    name: str
    histories: list[CharacterSkillHistoryEntry]


class IdeaHistoryEntry(Material):
    """知る相手を直すために、行を id で指せるアイデアの履歴の行(`ReadKnowableRows`)。"""

    id: int
    idea_id: int
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    name: str
    detail: str | None = None
    knowers: list[KnowerRow]


class KnowableRows(Material):
    # 人物を渡したときはその芯と来歴とスキルの来歴、アイデアを渡したときはその履歴だけが入る
    character: CharacterTextEntry | None = None
    character_histories: list[CharacterHistoryEntry]
    character_skills: list[CharacterSkillEntry]
    idea_histories: list[IdeaHistoryEntry]


class KnownCharacterHistory(Material):
    id: int
    character_id: int


class KnownCharacterSkillHistory(Material):
    id: int
    # スキルを持つ人物(知識整理の木の、人物の行に印を付ける)
    character_id: int


class KnownIdeaHistory(Material):
    id: int
    idea_id: int


class KnownRows(Material):
    """人物が知る相手の行(人物として直に入った行)を持つもの。場所として入った行は含まない(`ReadKnownRows`)。"""

    # 芯を知る人物の id
    character_ids: list[int]
    character_histories: list[KnownCharacterHistory]
    character_skill_histories: list[KnownCharacterSkillHistory]
    idea_histories: list[KnownIdeaHistory]
