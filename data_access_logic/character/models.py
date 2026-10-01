from typing import Any

from pydantic import field_validator, model_serializer

from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic.material import Material
from db.schema import ConfirmStatus, PersonalityLevel


class CharacterBase(Material):
    name: str | None = None
    kind: str
    text: str | None = None


class CharacterMaterial(CharacterBase):
    id: int
    confirmed: ConfirmStatus

    @field_validator("confirmed")
    @classmethod
    def _approved_only(cls, value: ConfirmStatus) -> ConfirmStatus:
        if value != ConfirmStatus.APPROVED:
            raise ValueError("ユーザが承認していない人物は話に出せない")
        return value


class ParticipantCharacter(CharacterBase):
    # 出来事の記録で、関わった人物・移動した人物を AI に id で選ばせる
    id: int


class CharacterParameterValues(Material):
    """期間ごとの行を重ねて決めた、ある時刻の値(`data_access_logic/character/parameters.py`)。"""

    family_name: str | None = None
    sex: str | None = None
    height: float | None = None
    build: str | None = None
    first_person: str | None = None
    second_person: str | None = None
    third_person: str | None = None
    tone: str | None = None
    dialect: str | None = None
    sincerity: PersonalityLevel = PersonalityLevel.NORMAL
    curiosity: PersonalityLevel = PersonalityLevel.NORMAL
    proactivity: PersonalityLevel = PersonalityLevel.NORMAL
    cooperativeness: PersonalityLevel = PersonalityLevel.NORMAL
    sociability: PersonalityLevel = PersonalityLevel.NORMAL
    emotional_expression: PersonalityLevel = PersonalityLevel.NORMAL
    self_esteem: PersonalityLevel = PersonalityLevel.NORMAL
    self_efficacy: PersonalityLevel = PersonalityLevel.NORMAL
    stress_resilience: PersonalityLevel = PersonalityLevel.NORMAL
    flexibility_of_values: PersonalityLevel = PersonalityLevel.NORMAL
    sensitivity: PersonalityLevel = PersonalityLevel.NORMAL
    imagination: PersonalityLevel = PersonalityLevel.NORMAL


class CharacterRelationLine(Material):
    """`common_query.character_relations_at_select` の一行。name1 から見た name2 との関係。"""

    name1: str | None = None
    name2: str | None = None
    relation: str
    text: str


class CharacterAt(Material):
    """ある時刻での人物。"""

    age: int | None = None
    parameters: CharacterParameterValues


class CastMaterial(CharacterAt):
    character: CharacterMaterial
    # 古い順
    recent_events: list[EventMaterial]


class MentionedMaterial(CharacterAt):
    """話に登場せず、プロット・本文に名前が出るだけの人物。"""

    character: CharacterMaterial


class CastCandidate(CharacterAt):
    """話の登場人物の候補。AI に id で選ばせる。"""

    character: ParticipantCharacter


class ParticipantMaterial(CharacterAt):
    character: ParticipantCharacter
    relations: list[CharacterRelationLine]
    # 新しい順
    recent_events: list[EventBase]


def _sheet(character: CharacterBase, at: CharacterAt) -> dict[str, Any]:
    parameters = at.parameters
    return {
        "名前": character.name,
        "種別": character.kind,
        "年齢": at.age,
        "名字": parameters.family_name,
        "性別": parameters.sex,
        "一人称": parameters.first_person,
        "二人称": parameters.second_person,
        "三人称": parameters.third_person,
        "口調": parameters.tone,
        "方言": parameters.dialect,
        "人物像": character.text,
    }


def relations_for_prompt(relations: list[CharacterRelationLine]) -> list[dict[str, Any]]:
    return [
        {"誰から": relation.name1, "誰へ": relation.name2, "関係": relation.relation, "説明": relation.text}
        for relation in relations
    ]


class CastSerialized(CastMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    recent_events: list[EventSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            **_sheet(self.character, self),
            "直近の出来事(古い順)": [event.model_dump() for event in self.recent_events],
        }


class MentionedSerialized(MentionedMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return _sheet(self.character, self)


class CastCandidateSerialized(CastCandidate):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {"人物id": self.character.id, **_sheet(self.character, self)}


class ParticipantSerialized(ParticipantMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        parameters = self.parameters
        return {
            "人物id": self.character.id,
            **_sheet(self.character, self),
            # 各軸は 無/低/並/高/必 の五段階
            "性格": {
                "誠実性": parameters.sincerity,
                "好奇心": parameters.curiosity,
                "行動力": parameters.proactivity,
                "協調性": parameters.cooperativeness,
                "社交性": parameters.sociability,
                "感情表現": parameters.emotional_expression,
                "自己肯定感": parameters.self_esteem,
                "自己効力感": parameters.self_efficacy,
                "ストレス耐性": parameters.stress_resilience,
                "価値観の柔軟性": parameters.flexibility_of_values,
                "感受性": parameters.sensitivity,
                "想像力": parameters.imagination,
            },
            "関係": relations_for_prompt(self.relations),
            "直近の出来事(新しい順)": [event.name for event in self.recent_events],
        }
