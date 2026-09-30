from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic.material import Material


class SeedText(Material):
    text: str


class StoredSeed(SeedText):
    id: int


class SeedPiles(Material):
    """棚卸しに回す種。`fresh` は棚卸し前、`settled` は棚卸し済み。どちらも id の順。"""

    fresh: list[StoredSeed]
    settled: list[StoredSeed]


class SeedMerge(Material):
    """一つにまとめる種の組と、まとめた種。"""

    ids: list[int]
    text: str


class ConsolidateRequest(Material):
    fresh: list[SeedText]
    settled: list[SeedText]


class ConsolidateRequestSerialized(ConsolidateRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。番号は新しい種から通しで振る。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "新しい種": [{"番号": number, "種": seed.text} for number, seed in enumerate(self.fresh, start=1)],
            "棚卸し済みの種": [{"番号": number, "種": seed.text}
                               for number, seed in enumerate(self.settled, start=len(self.fresh) + 1)],
        }


class SeedsDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    seeds: list[str] = Field(description="抜き出した出来事の種")

    @field_validator("seeds")
    @classmethod
    def _written(cls, value: list[str]) -> list[str]:
        return [seed.strip() for seed in value if seed.strip()]


class MergeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numbers: list[int] = Field(description="まとめる種の番号")
    text: str = Field(description="まとめた種")

    @field_validator("text")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


class ConsolidateDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    merges: list[MergeDraft] = Field(description="同じ出来事を言い換えただけの種の組")
