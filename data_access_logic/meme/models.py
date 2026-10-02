from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic.material import Material
from db.schema import MEME_CATEGORIES


class PooledMeme(Material):
    id: int
    category: str | None = None
    text: str


class DrawnMeme(Material):
    """引いたミームと、その人物の中での置き場所(古今表裏)。"""

    id: int
    position: str
    category: str | None = None
    text: str


class MemeText(Material):
    text: str


class MemeCategory(Material):
    """分類の空いたミームに振る分類。"""

    id: int
    category: str


class DedupeRequest(Material):
    fresh: list[str]
    existing: list[MemeText]


class DedupeRequestSerialized(DedupeRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "新しいミーム": [{"番号": number, "ミーム": text} for number, text in enumerate(self.fresh, start=1)],
            "既にあるミーム": [meme.text for meme in self.existing],
        }


class ClassifyRequest(Material):
    memes: list[MemeText]


class ClassifyRequestSerialized(ClassifyRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> list[dict[str, Any]]:
        return [{"番号": number, "ミーム": meme.text} for number, meme in enumerate(self.memes, start=1)]


class MemeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="ミームの一文")
    category: str = Field(description="分類", json_schema_extra={"enum": list(MEME_CATEGORIES)})

    @field_validator("text")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @property
    def known_category(self) -> str | None:
        """候補の外の分類が返ったときは空にして、後で振り直す。"""
        return self.category if self.category in MEME_CATEGORIES else None


class MemesDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    memes: list[MemeDraft] = Field(description="抜き出したミーム")

    @field_validator("memes")
    @classmethod
    def _written(cls, value: list[MemeDraft]) -> list[MemeDraft]:
        return [meme for meme in value if meme.text]


class DedupeDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    duplicates: list[int] = Field(description="重複している新しいミームの番号")


class CategoryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="ミームの番号")
    category: str = Field(description="分類", json_schema_extra={"enum": list(MEME_CATEGORIES)})


class ClassifyDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    categories: list[CategoryDraft] = Field(description="ミームごとの分類")
