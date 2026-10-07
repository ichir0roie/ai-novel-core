from pydantic import ConfigDict

from data_access_logic.knowers import KnowerRow
from data_access_logic.material import Dated, Form, Material, Timestamp


class LocationHistoryRow(Form):
    """場所の来歴の行(id と location_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    # 起きた年。同じ年のことは一行にまとめる。空なら年が決まっていない(話・出来事には渡さない)
    start: int | None = None
    description: str
    # 知る相手。この相手だけが来歴を知る。渡さなければ、新しい行はその場所(住む人物が知る)、今ある行はそのまま
    # (`db/child_lists.py` の `replaced_histories`)
    knowers: list[KnowerRow] | None = None


class LocationRecord(Dated):
    id: int
    name: str | None = None
    kind: str | None = None
    parent_id: int | None = None
    location_world: float | None = None
    location_planet: int | None = None
    location_longitude: float | None = None
    location_latitude: float | None = None
    location_altitude: float | None = None
    polygon: dict | None = None
    area: float | None = None
    environment: str | None = None
    sample_region: str | None = None
    sample_culture: str | None = None
    sample_era: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    active_random_generation: bool
    histories: list[LocationHistoryRow]
    text: str


class DeletedLocation(Material):
    id: int
    name: str | None = None
    kind: str | None = None
