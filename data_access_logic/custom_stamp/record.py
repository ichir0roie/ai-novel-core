from typing import Any

from pydantic import ConfigDict, Field, field_validator

from data_access_logic.material import Form, Material
from db.stamp import Stamp


class CustomStampMonthRow(Form):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    # 今ある月の行を指す(GUI が子の行の配列を返すとき)。月の順(`number`)は並びの順で振り直す
    id: int | None = None
    # 並びの順で振り直すので、渡しても使わない
    number: int | None = None
    days: int = Field(ge=1)
    name: str | None = None
    # 月の終わりの、週に数えない日の数
    outside_week_days: int = Field(default=0, ge=0)


def _western(value: Any) -> Any:
    # 暦の 0 年 1 月 1 日に当たる時刻(offset)は、どの暦でもなく西暦で出し入れする
    return value.western_text() if isinstance(value, Stamp) else value


class CustomStampRecord(Material):
    id: int
    name: str
    # 西暦
    offset: str
    hours_per_day: int
    minutes_per_hour: int
    seconds_per_minute: int
    days_per_week: int
    months: list[CustomStampMonthRow]

    @field_validator("offset", mode="before")
    @classmethod
    def _offset(cls, value: Any) -> Any:
        return _western(value)


class DeletedCustomStamp(Material):
    id: int
    name: str
