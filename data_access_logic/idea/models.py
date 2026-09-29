from typing import Any

from pydantic import model_serializer

from ai.time_keeper import constants
from data_access_logic.material import Material
from db.stamp import Stamp


class IdeaMaterial(Material):
    id: int
    name: str
    kind: str
    text: str | None = None
    start: Stamp | None = None
    parent_idea_id: int | None = None


class IdeaRecognitionMaterial(Material):
    idea_id: int
    name: str
    detail: str | None = None


class IdeaTerm(Material):
    """`idea_search.terms_of` がそろえた語。"""

    keyword: str
    variants: list[str]
    description: str
    coined: bool
    kind: str
    start: Stamp | None = None
    end: Stamp | None = None


class RelatedIdeaMaterial(Material):
    idea: IdeaMaterial
    # その場所・時代で使う呼び名(`idea_alias.called` が選んだ行)。無ければ本質の名前で呼ぶ
    recognition: IdeaRecognitionMaterial | None = None


class IdeaContextMaterial(Material):
    # 下書きの語が当たったアイデア
    hits: list[IdeaMaterial]
    # どのアイデアにも当たらなかった造語から足した、未確認のアイデア
    candidates: list[IdeaMaterial]
    # 清書に渡す。hits(時期の決まったもの)とその上位・下位
    related: list[RelatedIdeaMaterial]

    @property
    def linked(self) -> list[IdeaMaterial]:
        return list({idea.id: idea for idea in self.hits + self.candidates}.values())


class IdeaContextSerialized(IdeaContextMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> list[dict[str, Any]]:
        rows = []
        for related in self.related:
            idea, recognition = related.idea, related.recognition
            text = idea.text or ""
            if len(text) > constants.IDEA_CONTEXT_LETTERS:
                text = text[:constants.IDEA_CONTEXT_LETTERS] + "…"
            rows.append({
                "名前": recognition.name if recognition else idea.name,
                "種類": idea.kind,
                "作中での受け止め方": recognition.detail if recognition else None,
                "内容": text,
            })
        return rows
