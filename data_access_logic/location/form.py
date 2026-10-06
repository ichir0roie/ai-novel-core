from typing import Any

from pydantic import Field, field_validator

from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.material import Form, Timestamp
from db.polygon import parse_polygon


class _LocationColumns(Form):
    parent_id: int | None = None
    location_world: float | None = None
    location_planet: int | None = None
    location_longitude: float | None = None
    location_latitude: float | None = None
    location_altitude: float | None = None
    # GeoJSON の Polygon か、[経度, 緯度] の環の並び
    polygon: dict | None = None
    area: float | None = None
    environment: str | None = None
    sample_region: str | None = None
    sample_culture: str | None = None
    sample_era: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None

    @field_validator("polygon", mode="before")
    @classmethod
    def _polygon(cls, value: Any) -> dict | None:
        return parse_polygon(value)


class LocationCreateForm(_LocationColumns):
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    text: str = ""
    active_random_generation: bool = False
    # 来歴(起きた年ごとの行)
    histories: list[LocationHistoryRow] = []


class LocationUpdateForm(_LocationColumns):
    id: int
    name: str | None = None
    kind: str | None = None
    text: str | None = None
    active_random_generation: bool | None = None
    # 渡せば来歴の行をまるごと置き換える
    histories: list[LocationHistoryRow] | None = None
