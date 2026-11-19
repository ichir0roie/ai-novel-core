from pydantic import Field

from data_access_logic.custom_stamp.record import CustomStampMonthRow
from data_access_logic.material import Form


class CustomStampCreateForm(Form):
    name: str = Field(min_length=1)
    # この暦で数え始める西暦の時刻(`5000/01/01`)
    offset: str = Field(min_length=1)
    hours_per_day: int = Field(default=24, ge=1)
    minutes_per_hour: int = Field(default=60, ge=1)
    seconds_per_minute: int = Field(default=60, ge=1)
    days_per_week: int = Field(default=7, ge=1)
    months: list[CustomStampMonthRow] = Field(min_length=1)


class CustomStampUpdateForm(Form):
    id: int
    name: str | None = Field(default=None, min_length=1)
    offset: str | None = Field(default=None, min_length=1)
    hours_per_day: int | None = Field(default=None, ge=1)
    minutes_per_hour: int | None = Field(default=None, ge=1)
    seconds_per_minute: int | None = Field(default=None, ge=1)
    days_per_week: int | None = Field(default=None, ge=1)
    # 渡すと配列をまるごと置き換える
    months: list[CustomStampMonthRow] | None = Field(default=None, min_length=1)
