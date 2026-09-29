import unicodedata
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, field_validator, model_serializer, model_validator

from data_access_logic import constants
from data_access_logic.material import Material
from db.schema import ConfirmStatus
from db.stamp import Stamp, StampError


class IdeaMaterial(Material):
    id: int
    name: str
    kind: str
    confirmed: ConfirmStatus
    text: str | None = None
    start: Stamp | None = None
    parent_idea_id: int | None = None


class IdeaRecognitionMaterial(Material):
    idea_id: int
    name: str
    detail: str | None = None


def normalized(text: str | None) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


# kind を付けずに渡された語を、自動で足すときの種別
DEFAULT_KIND = "概念"
# 一字の言い換えは、ほかの語の一部(「官」と「器官」など)に当たりすぎる。
_MIN_VARIANT_LETTERS = 2


def _stamp_or_none(value: Any) -> Stamp | None:
    try:
        return Stamp.parse(value)
    except (StampError, TypeError):
        return None


class IdeaTerm(Material):
    """アイデアと照らす語。claude が渡す語も、AI が挙げた語(`IdeaTermDraft`)も、この形で扱う。"""

    keyword: str
    variants: list[str] = []
    description: str = ""
    # 無ければ true(claude が自分で選んで渡した語は、固有の語として扱う)
    coined: bool = True
    kind: str = DEFAULT_KIND
    start: Stamp | None = None
    end: Stamp | None = None

    @field_validator("keyword", mode="before")
    @classmethod
    def _keyword(cls, value: Any) -> str:
        keyword = normalized(value if isinstance(value, str) else "")
        if not keyword:
            raise ValueError("keyword が空")
        return keyword

    @field_validator("variants", mode="before")
    @classmethod
    def _variants(cls, value: Any) -> list[str]:
        return [normalized(variant) for variant in value or [] if isinstance(variant, str)]

    @field_validator("description", mode="before")
    @classmethod
    def _description(cls, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @field_validator("coined", mode="before")
    @classmethod
    def _coined(cls, value: Any) -> bool:
        return value is not False

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> str:
        return normalized(value if isinstance(value, str) else "") or DEFAULT_KIND

    @field_validator("start", "end", mode="before")
    @classmethod
    def _stamp(cls, value: Any) -> Stamp | None:
        return _stamp_or_none(value)

    @model_validator(mode="after")
    def _consistent(self) -> "IdeaTerm":
        self.variants = [variant for variant in dict.fromkeys(self.variants)
                         if len(variant) >= _MIN_VARIANT_LETTERS and variant != self.keyword]
        if self.start is not None and self.end is not None and self.end <= self.start:
            self.end = None
        return self


def unique_terms(terms: list[IdeaTerm]) -> list[IdeaTerm]:
    """同じ keyword の語は、先に挙げたものだけを残す。"""
    found: dict[str, IdeaTerm] = {}
    for term in terms:
        found.setdefault(term.keyword, term)
    return list(found.values())


# AI には時期を文字列で書かせ、`IdeaTerm` のバリデータで `Stamp` に読む
_StampText = Annotated[Stamp | None, WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}]})]


class IdeaTermDraft(IdeaTerm):
    # AI にはすべての欄を書かせる。整え方は `IdeaTerm` のバリデータのまま
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(description="語")
    variants: list[str] = Field(description=(
        "keyword の表記揺れ・同義語・上位語・作中の人が使いそうな呼び方を 2〜6 個。"
        "部分一致で検索するので、keyword を組み立てている 2〜3 字の核の語を必ず含める。1 字の語は使わない"))
    description: str = Field(description="この文の中でその語が何を指しているかの一文")
    coined: bool = Field(description="その語がこの世界・作品に固有の語(作中の呼び名・造語・固有の技術や制度の名)なら true、一般の語なら false")
    kind: str = Field(description="その語の種別。「技術」「制度」「概念」「呼称」「現象」「施設」「時代」などの短い語で一つ")
    start: _StampText = Field(description=(
        "その事柄がこの世界に現れた(作られた・始まった・そう呼ばれ始めた)時期。"
        "文の時刻と文の中身から、ある程度はっきり言えるときだけ「年」か「年/月/日」で書く。はっきり言えなければ null"))
    end: _StampText = Field(description="その事柄が終わった・廃れた・そう呼ばれなくなった時期。文から分かるときだけ start と同じ形で書き、分からなければ null")


class IdeaTermsDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    terms: list[IdeaTermDraft] = Field(description="設定資料と照らし合わせる語。0〜8 件")

    @field_validator("terms", mode="before")
    @classmethod
    def _without_blank_keyword(cls, value: Any) -> Any:
        # keyword が空白だけの語は、応答ごと捨てずにその語だけを落とす
        if not isinstance(value, list):
            return value
        return [term for term in value
                if not (isinstance(term, dict) and isinstance(term.get("keyword"), str) and not normalized(term["keyword"]))]


class RelatedIdeaMaterial(Material):
    idea: IdeaMaterial
    # その場所・時代で使う呼び名(`alias.called` が選んだ行)。無ければ本質の名前で呼ぶ
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


class IdeaHit(Material):
    """当たったアイデアと、当たり方の強さ・当たった語。"""

    idea: IdeaMaterial
    score: int
    keywords: list[str]
