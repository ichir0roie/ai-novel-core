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

from data_access_logic.ai_client import AIClient
from data_access_logic.character.generator_models import (
    BirthLocationMaterial, CharacterBirthMaterial, HistoryItemDraft, NearbyCharacter, NonPersonContentDraft,
    PersonContentDraft,
)
from data_access_logic.character.histories import histories_for_prompt
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized, IdeaMaterial
from data_access_logic.material import Material
from db.schema import StyleScope
from db.stamp import Stamp

logger = logging.getLogger(__name__)


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
                {"名前": idea.name, "種類": idea.kind, "始まる年": idea.first_start.year if idea.first_start else None}
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
        "\n".join([request.model_dump_json(indent=2), "この一件を検める。"]), output, instruction=StyleScope.CHARACTER_CONSISTENCY)
    if draft is None or not draft.issues or not draft.text.strip():
        return Reconciled(text=text, principle=content.principle, history=history)
    logger.info("世界・設定との食い違いを直した:\n" + "".join(f"    {issue}\n" for issue in draft.issues))
    if isinstance(draft, PersonConsistencyDraft):
        history = draft.history
    return Reconciled(text=draft.text.strip(), principle=draft.principle.strip(), history=history)
