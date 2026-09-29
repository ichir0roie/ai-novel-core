from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer, PlainValidator, WithJsonSchema

from db.stamp import Stamp


class Material(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class Form(BaseModel):
    """入口の引数。スキーマに無い欄が混ざっていたら止める。"""

    model_config = ConfigDict(extra="forbid")

    def column_values(self, model: Any) -> dict[str, Any]:
        """欄のうち `model` のテーブルの列に当たるもの。親子の配列・誕生没年などの列でない欄は、呼ぶ側が別に書く。"""
        columns = model.__table__.columns
        return {name: getattr(self, name) for name in type(self).model_fields if name != "id" and name in columns}

    def changed_column_values(self, model: Any) -> dict[str, Any]:
        """`column_values` のうち、渡された欄だけ(修正の入口は渡した欄だけを直す)。"""
        columns = model.__table__.columns
        return {name: getattr(self, name) for name in self.model_fields_set if name != "id" and name in columns}


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
