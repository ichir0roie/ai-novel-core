"""人物モード(`ActCharacter`)の材料と、AI の出力の形。

人物の目(狙う段)には、その人物が知ることのできるデータ(`character/knowledge.py`)と、目の前の様子だけを渡す。
作者の目(裁く段)には、場所の状況(出来事の生成と同じ `LocationSituationSerialized`)と、人物の狙いを渡す。
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.knowledge import AppearanceSerialized, KnowledgeSerialized
from data_access_logic.character.record import CharacterMove, GeneratedCharacter
from data_access_logic.event.progress_models import (
    EventRecordDraft, LocationSituationMaterial, LocationSituationSerialized,
)
from data_access_logic.event.record import EventRecord
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material, Timestamp
from db.stamp import Stamp


class ActorPick(BaseModel):
    """動く人物と、動く時刻・場所。"""

    character_id: int
    name: str | None = None
    time: Timestamp
    location_id: int


class PresentPerson(Material):
    character_id: int
    # 知り合いでなければ名前は分からない
    name: str | None = None
    looks: AppearanceSerialized


class OpenArc(Material):
    """人物がまだ追っている筋(終わりの空いた、親の出来事)。"""

    id: int
    name: str
    text: str


class ActorSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。人物が知ることは整形した形で組むので、db の側で dump して
    `ActorBrief.prompt` に入れて運ぶ。"""

    time: Timestamp
    location_name: str | None = None
    knowledge: KnowledgeSerialized
    present: list[PresentPerson]
    # この場所の直近の出来事の名前(新しい順)
    recent_events: list[str]
    arcs: list[OpenArc]
    # ほかの場面の筋から時代・場所・固有名詞を抜いたもの。思いつきの元
    seeds: list[str]
    # 作者からの軽い方向づけ
    nudge: str | None = None

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "いまの時刻": str(self.time),
            "いる場所": self.location_name,
            "あなたが知っていること": self.knowledge.model_dump(),
            "目の前にいる人物": [
                {"人物id": person.character_id, "名前": person.name or "(名を知らない)", **person.looks.model_dump()}
                for person in self.present],
            "この場所で近ごろ起きたこと(新しい順)": self.recent_events,
            "あなたが追っている企て": [{"企てid": arc.id, "名前": arc.name, "狙い": arc.text} for arc in self.arcs],
            "思いつきの元": self.seeds,
            "作者からの方向づけ": self.nudge,
        }


class ActorBrief(BaseModel):
    """狙う段の材料(段の出力。web では JSON で運ぶ)。"""

    # 人物の目で整形した材料(`ActorSerialized` を dump したもの)
    prompt: dict[str, Any]
    # 居合わせる人物(動く人物は含まない)
    present_ids: list[int]
    arcs: list[OpenArc]


class IntentDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    inner: str = Field(description="いまの内心。何を感じ、何を考えているか")
    aim: str = Field(description="この一手で果たしたいこと(狙い)")
    action: str = Field(description="実際にすること。誰に・どこで・何をするか")
    speech: str | None = Field(description="口にする言葉。黙って動くなら null")
    arc_id: int | None = Field(description="追っている企てを続ける一手なら、その企てid。続けないなら null")
    new_arc_name: str | None = Field(
        description="この一手が、何度も手を重ねて果たす新しい企ての始まりなら、その企ての短い名前。そうでなければ null")

    @field_validator("aim", "action")
    @classmethod
    def _filled(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("空")
        return value

    def as_text(self) -> str:
        lines = [f"狙い: {self.aim}", f"行動: {self.action}"]
        if self.speech:
            lines.append(f"言葉: 「{self.speech}」")
        return "\n".join(lines)


class ActIdeaDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(description="この一手で生まれた・広まった事柄(技術・制度・概念・呼称・噂など)の本質の名前")
    kind: str = Field(description="種別。「技術」「制度」「概念」「呼称」「現象」「施設」などの短い語で一つ")
    description: str = Field(description="その事柄の本質。作者だけが読む説明")
    called: str = Field(description="作中でこの場所の人がそれを呼ぶ名前")
    detail: str = Field(description="作中の人がそれについて知っている・信じていること")
    knower_ids: list[int] = Field(description="それを知った人物の人物id。居合わせる人物・対象の中からだけ選ぶ")


class NewCharacterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="この一手で新しく現れる人物・対象の人物像と役どころ(生まれた子・雇った者・作った組織など)")
    person: bool = Field(description="人物なら true、組織・集団・物など人物以外なら false")
    relation: str = Field(description="動いた人物から見た、その人物・対象との間柄の短い名前(子・雇い人・創った組織など)")


class ActOutcomeDraft(EventRecordDraft):
    ideas: list[ActIdeaDraft] = Field(
        description=f"この一手で生まれた・広まった事柄。無ければ空。{constants.ACT_NEW_IDEA_LIMIT}件まで")
    new_characters: list[NewCharacterDraft] = Field(
        description=f"この一手で新しく現れる人物・対象。無ければ空。{constants.ACT_NEW_CHARACTER_LIMIT}件まで")
    arc_closed: bool = Field(description="続けた企てが、この一手で果たされたか潰えたか")


class OutcomeRequest(Material):
    situation: LocationSituationMaterial
    destinations: list[LocationMaterial]
    actor_name: str | None = None
    intent: IntentDraft
    roll: str
    arc: OpenArc | None = None


class OutcomeRequestSerialized(OutcomeRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    situation: LocationSituationSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "場所の状況": self.situation.model_dump(),
            "移動先の候補": [{"場所id": destination.id, "名前": destination.name, "種別": destination.kind}
                        for destination in self.destinations],
            "動いた人物": self.actor_name,
            "人物の内心": self.intent.inner,
            "人物の狙いと行動": self.intent.as_text(),
            "続けた企て": None if self.arc is None else {"名前": self.arc.name, "狙い": self.arc.text},
            "サイコロで決まった成り行き": self.roll,
        }


class ActSaveForm(BaseModel):
    actor_id: int
    time: Stamp
    location_id: int
    participant_ids: list[int]
    destinations: list[LocationMaterial]
    intent: IntentDraft
    outcome: ActOutcomeDraft


class ActSaved(BaseModel):
    event: EventRecord
    # 一手が続けた・始めた企て(親の出来事)。無ければ None
    arc_id: int | None = None
    idea_ids: list[int] = []
    moves: list[CharacterMove] = []


class NewCharacterLink(BaseModel):
    actor_id: int
    character_id: int
    event_id: int
    relation: str
    time: Stamp


class ActedCharacter(BaseModel):
    expansion_id: int
    actor: ActorPick
    intent: IntentDraft
    roll: str
    event: EventRecord
    arc_id: int | None = None
    idea_ids: list[int] = []
    characters: list[GeneratedCharacter] = []
    moves: list[CharacterMove] = []
