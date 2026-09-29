from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, PlainSerializer, PlainValidator, WithJsonSchema

from db.stamp import Stamp


class Material(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    # このモデルに詰めるのに要る、noload のリレーションの読み方(`entrypoint.record_of` / `entrypoint.loading` が使う)
    LOAD_OPTIONS: ClassVar[tuple] = ()


class Form(BaseModel):
    """入口の引数。スキーマに無い欄が混ざっていたら止める。"""

    model_config = ConfigDict(extra="forbid")

    def write_to(self, record: Any) -> None:
        """欄のうち `record` のテーブルの列に当たるものを書く。親子の配列・誕生没年などの列でない欄は、呼ぶ側が別に書く。"""
        columns = type(record).__table__.columns
        for name, value in self:
            if name != "id" and name in columns:
                setattr(record, name, value)

    def write_changes_to(self, record: Any) -> None:
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
