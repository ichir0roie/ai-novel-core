from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, PlainSerializer, PlainValidator, WithJsonSchema, model_validator

from db.schema import Base
from db.stamp import Stamp


class Material(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    # このモデルに詰めるのに要る、noload のリレーションの読み方(`entrypoint.record_of` / `entrypoint.loading` が使う)
    LOAD_OPTIONS: ClassVar[tuple] = ()


class Named(Material):
    """行を id と名前だけで指す。"""

    id: int
    name: str | None = None


@dataclass(frozen=True)
class References:
    """`Annotated` に添えて、欄が指す行のテーブルを表す(`Annotated[int | None, References("location")]`)。"""

    table: str


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class Draft(BaseModel):
    """GUI の欄・スキルの引数で渡る下書き。空の欄(None・空白だけの文字列)は、渡さなかったのと同じ扱いにする。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="before")
    @classmethod
    def _unset_blanks(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {key: item for key, item in value.items() if not _blank(item)}


class Form(BaseModel):
    """入口の引数。スキーマに無い欄が混ざっていたら止める。"""

    model_config = ConfigDict(extra="forbid")

    def write_to(self, record: Base) -> None:
        """欄のうち `record` のテーブルの列に当たるものを書く。親子の配列・誕生没年などの列でない欄は、呼ぶ側が別に書く。"""
        columns = type(record).__table__.columns
        for name, value in self:
            if name != "id" and name in columns:
                setattr(record, name, value)

    def write_changes_to(self, record: Base) -> None:
        """`write_to` のうち、渡された欄だけを書く(修正の入口は渡した欄だけを直す)。"""
        columns = type(record).__table__.columns
        for name in self.model_fields_set:
            if name != "id" and name in columns:
                setattr(record, name, getattr(self, name))


def _stamp(value: Any) -> Stamp:
    stamp = Stamp.parse(value)
    if stamp is None:
        raise ValueError("時刻が空")
    return stamp


# 入口の引数(`"11579/03/02"` などの文字列)から読み、レスポンス(`model_dump(mode="json")`)では文字列に戻す。
# python のまま dump すると Stamp のまま残るので、db へ書く値にそのまま使える
Timestamp = Annotated[
    Stamp, PlainValidator(_stamp), PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string"})]
