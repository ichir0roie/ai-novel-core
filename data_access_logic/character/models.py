from typing import Any

from pydantic import model_serializer

from data_access_logic.character.histories import histories_for_prompt
from data_access_logic.history_start import start_for_prompt
from data_access_logic.character.record import CharacterHistoryRow, CharacterRelationHistoryRow
from data_access_logic.event.models import EventBase, EventMaterial, EventSerialized
from data_access_logic import constants
from data_access_logic.knowers import KnowerMaterial, secret_for_prompt
from data_access_logic.material import Material, Timestamp
from db.schema import PersonalityLevel


class CharacterBase(Material):
    name: str | None = None
    kind: str
    # 人物の芯(経歴・立場・性格の説明)。いつの話・出来事にも渡す
    text: str | None = None


class CharacterWholeBase(CharacterBase):
    """作者の目で人物を書くときに渡す、本文のすべての列。"""

    appearance: str | None = None
    meme: str | None = None
    principle: str | None = None
    plot: str | None = None


class CharacterMaterial(CharacterWholeBase):
    id: int


class ParticipantCharacter(CharacterWholeBase):
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


PERSONALITY_LABELS = {
    "sincerity": "誠実性",
    "curiosity": "好奇心",
    "proactivity": "行動力",
    "cooperativeness": "協調性",
    "sociability": "社交性",
    "emotional_expression": "感情表現",
    "self_esteem": "自己肯定感",
    "self_efficacy": "自己効力感",
    "stress_resilience": "ストレス耐性",
    "flexibility_of_values": "価値観の柔軟性",
    "sensitivity": "感受性",
    "imagination": "想像力",
}


def personality_for_prompt(parameters: CharacterParameterValues) -> dict[str, PersonalityLevel]:
    # 各軸は 無/低/並/高/必 の五段階
    return {label: getattr(parameters, name) for name, label in PERSONALITY_LABELS.items()}


class RelationParty(Material):
    id: int
    name: str | None = None


class CharacterRelationLine(Material):
    """ある時刻に続いている関係。`character_1` から見た `character_2` との関係。"""

    character_1: RelationParty
    character_2: RelationParty
    relation: str
    # 関係の芯(時期を限らない)
    text: str
    # その時刻の年までに起きた来歴(古い順。`cast.relations_at`)。先の時刻の行と、年の決まっていない行は入らない
    histories: list[CharacterRelationHistoryRow]


class CharacterAt(Material):
    """ある時刻での人物。"""

    age: int | None = None
    parameters: CharacterParameterValues
    # その時刻までに起きた来歴(`histories_at`)。先の時刻の行、終わった行と、年の決まっていない行は入らない
    histories: list[CharacterHistoryRow]


class HistoryMaterial(Material):
    """作者の目で読むスキルの来歴の行。"""

    start: Timestamp | None = None
    description: str
    # その時刻までに知った相手(`knowers.knowers_at`)
    knowers: list[KnowerMaterial]


class CharacterHistoryMaterial(HistoryMaterial):
    """作者の目で読む人物の来歴の行。"""

    # 装い・持ち物・記憶・隠し事など。空なら起きた出来事
    kind: str | None = None


class CharacterSkillMaterial(Material):
    """作者の目で読むスキル。"""

    name: str
    # スキルの本質。作者だけが読む
    text: str
    # その時刻までに起きた来歴(`skills.rows_at`)。知る相手に関わらずすべて
    histories: list[HistoryMaterial]


class CharacterSecrets(Material):
    """人物の来歴・スキルを、誰が知っているか。本文を書く Claude の材料に添える(`cast.secrets_at`)。"""

    # その時刻までに起きて、まだ終わっていない来歴(`histories.rows_at`)。知る相手に関わらずすべて
    histories: list[CharacterHistoryMaterial]
    # その時刻までに来歴の行が始まったスキル(まだ持っていないスキルは入らない)
    skills: list[CharacterSkillMaterial]


def _dated_histories_for_prompt(histories: list[HistoryMaterial]) -> list[dict[str, Any]]:
    lines = []
    for history in histories:
        secret = secret_for_prompt(history.knowers)
        lines.append({"時期": start_for_prompt(history.start), "来歴": history.description,
                      **({} if secret is None else {"秘密": secret})})
    return lines


def _brief_histories(histories: list[CharacterHistoryMaterial]) -> list[CharacterHistoryMaterial]:
    # 筋に効くのは直近の出来事と今の装い・持ち物なので、古い出来事は渡さない
    events = [history for history in histories if history.kind is None]
    recent = {id(history) for history in events[-constants.EPISODE_BRIEF_HISTORY_LIMIT:]}
    return [history for history in histories if history.kind is not None or id(history) in recent]


def secrets_for_prompt(secrets: CharacterSecrets) -> dict[str, Any]:
    """`_sheet` の来歴を、直近の行と、秘密の行には誰だけが知るかを添えた形に置き換える。"""
    histories = _brief_histories(secrets.histories)
    return {
        "来歴(古い順)": [{"種別": history.kind, **line}
                       for history, line in zip(histories, _dated_histories_for_prompt(histories))],
        "スキル": [{"名前": skill.name, "本質": skill.text, "来歴(古い順)": _dated_histories_for_prompt(skill.histories)}
                 for skill in secrets.skills],
    }


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


def _sheet(character: CharacterWholeBase, at: CharacterAt) -> dict[str, Any]:
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
        "体格": parameters.build,
        "外見": character.appearance,
        "人物像": character.text,
        "ミーム": character.meme,
        "行動原理": character.principle,
        "筋書き": character.plot,
        "来歴(古い順)": histories_for_prompt(at.histories),
    }


def relations_for_prompt(relations: list[CharacterRelationLine]) -> list[dict[str, Any]]:
    return [
        {"誰から": relation.character_1.name, "誰へ": relation.character_2.name, "関係": relation.relation,
         "説明": relation.text,
         "来歴(古い順)": [{"時期": start_for_prompt(history.start), "来歴": history.description}
                         for history in relation.histories]}
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
        # 語り部は、話の時刻より先の筋(筋書き)も、来歴も読まない。人物のこれまでは、関わった話の本文から読む
        sheet = {key: value for key, value in _sheet(self.character, self).items()
                 if key not in ("筋書き", "来歴(古い順)")}
        return {"人物id": self.character.id, **sheet}


class CastingCandidate(Material):
    """登場人物の候補(結ぶかどうかを決めるだけの人物)。"""

    character: CharacterMaterial
    age: int | None = None


class CastingCandidateSerialized(CastingCandidate):
    """このセッションの Claude が読む形に整形する。結ぶかを決めるのに要る名前と人物像だけを渡す。"""

    @model_serializer
    def _for_claude(self) -> dict[str, Any]:
        return {"人物id": self.character.id, "名前": self.character.name, "種別": self.character.kind,
                "年齢": self.age, "人物像": self.character.text}


class ParticipantSerialized(ParticipantMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "人物id": self.character.id,
            **_sheet(self.character, self),
            "性格": personality_for_prompt(self.parameters),
            "関係": relations_for_prompt(self.relations),
            "直近の出来事(新しい順)": [event.name for event in self.recent_events],
        }
