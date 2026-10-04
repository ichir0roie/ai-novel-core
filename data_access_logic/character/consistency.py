#!/usr/bin/env python3
"""生んだ人物・対象を足す前に、世界と食い違っていないかを AI に検めさせ、食い違えば直させる。

承認を置かず、生んだものはそのまま世界に出るので、足す前のこの段が世界の崩れを止める。
検めるのは、居場所(生成した場所に今いること)・時刻(現在より後のこと)・まだ無い設定・関係する設定・既にいる人物や対象との食い違い。
関係する設定(説明の語をアイデアと照らしたもの)を踏まえた直しも、同じ一回の呼び出しで行う。
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from ai.instructions.naming import NAME_PLACEHOLDER
from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator_models import (
    BirthLocationMaterial, CharacterBirthMaterial, HistoryItemDraft, NearbyCharacter, NonPersonContentDraft,
    PersonContentDraft,
)
from data_access_logic.character.histories import histories_for_prompt
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized, IdeaMaterial
from data_access_logic.material import Material
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の整合を検める校閲者です。
新しく生まれた人物・対象1件の説明・行動原理・来歴と、それを足す世界の材料を渡すので、世界と食い違うところを探し、食い違いだけを直してください。
検めること:
- 居場所: この一件は「居場所」で生まれ(成り立ち)、現在の時刻もそこ(かその中の場所)で暮らし・働いている。現在の住まい・仕事場・拠点が別の場所になっていれば食い違い。
  居場所でその役を担う形に移すか、居場所から通う・関わる形に直す。一時よそへ出た来歴はよいが、現在は居場所にいるようにする
- 時刻: 現在の時刻より後のこと(後年の立場・行く末・死、「のちに」「やがて」)が書かれていれば食い違い。消す
- まだ無い設定: 「この時刻より後に始まる設定(まだ無い)」に当たる立場・組織・技術・出来事が、現在や来歴に出ていれば食い違い。消すか、まだ無い形に直す
- 関係する設定: 説明の語に当たった世界の設定(名前・種類・この場所・時代での呼び名と受け止め方)。呼び名・受け止め方と食い違う書き方があれば食い違い。
  設定の呼び名で言い換えると具体的になる語も、その呼び名に直してよい(これも issues に1件として書く)
- 既にいる人物・対象: その説明・来歴と食い違う関係・出来事(相手の来歴に無い親子・師弟、相手と同じ唯一の地位など)があれば食い違い。食い違わない形に直す
食い違いの無いところは、言い回しも長さも変えない。人物像・性格・生い立ちの核は保つ。
説明の中でこの一件を指す「{NAME_PLACEHOLDER}」はそのまま残す。
食い違いが無ければ、issues を空にし、渡したものをそのまま返す。"""


class ConsistencyRequest(Material):
    time: Stamp
    kind: str
    age: int
    born_location: BirthLocationMaterial | None = None
    later_ideas: list[IdeaMaterial]
    ideas: IdeaContextMaterial
    nearby_characters: list[NearbyCharacter]
    text: str
    principle: str
    history: Sequence[HistoryItemDraft]


class ConsistencyRequestSerialized(ConsistencyRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    ideas: IdeaContextSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        location = self.born_location
        return {
            "現在の時刻": str(self.time),
            "居場所": {
                "名前": location.name,
                "種別": location.kind,
                "説明": location.text,
                "所属する地域": f"{location.parent.name}({location.parent.kind})" if location.parent else None,
            } if location else None,
            "この時刻より後に始まる設定(まだ無い)": [
                {"名前": idea.name, "種類": idea.kind, "始まる年": idea.start.year if idea.start else None}
                for idea in self.later_ideas],
            "関係する設定": self.ideas.model_dump(),
            "既にいる人物・対象": [
                {"名前": character.name, "種別": character.kind, "説明": character.text,
                 "来歴(古い順)": histories_for_prompt(character.histories)}
                for character in self.nearby_characters],
            "検める一件": {
                "種別": self.kind,
                "年齢": self.age,
                "説明": self.text,
                "行動原理": self.principle,
                "来歴": [{"歳": item.age, "内容": item.text} for item in self.history],
            },
        }


class ConsistencyDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    issues: list[str] = Field(description="見つけた食い違い。1件を1文で。無ければ空の配列")
    text: str = Field(description="直した説明。食い違いが無ければ渡した説明をそのまま")
    principle: str = Field(description="直した行動原理。食い違いが無ければ渡した行動原理をそのまま(空なら空)")


class PersonConsistencyDraft(ConsistencyDraft):
    history: list[HistoryItemDraft] = Field(description="直した来歴(歳の順)。食い違いが無ければ渡した来歴をそのまま")


class Reconciled(Material):
    """世界と食い違わないよう検めた説明・行動原理・来歴。"""

    text: str
    principle: str
    history: Sequence[HistoryItemDraft]


def reconciled(
    ai: AIClient, material: CharacterBirthMaterial, kind: str, age: int, content: PersonContentDraft | NonPersonContentDraft,
    ideas: IdeaContextMaterial,
) -> Reconciled:
    """`ideas` は説明の語をアイデアと照らしたもの。AI が答えないか食い違いが無ければ、渡したままを返す。"""
    text = content.text
    history: Sequence[HistoryItemDraft] = content.history if isinstance(content, PersonContentDraft) else []
    request = ConsistencyRequestSerialized(
        time=material.time, kind=kind, age=age, born_location=material.born_location,
        later_ideas=material.later_ideas, ideas=ideas, nearby_characters=material.nearby_characters,
        text=text, principle=content.principle, history=history)
    output = PersonConsistencyDraft if isinstance(content, PersonContentDraft) else ConsistencyDraft
    draft = ai.generate(
        "\n".join([request.model_dump_json(indent=2), "この一件を検めてください。"]), output, system=_SYSTEM_PROMPT)
    if draft is None or not draft.issues or not draft.text.strip():
        return Reconciled(text=text, principle=content.principle, history=history)
    logger.info("世界・設定との食い違いを直した:\n" + "".join(f"    {issue}\n" for issue in draft.issues))
    if isinstance(draft, PersonConsistencyDraft):
        history = draft.history
    return Reconciled(text=draft.text.strip(), principle=draft.principle.strip(), history=history)
