from data_access_logic.location.record import LocationHistoryRow
from data_access_logic.material import Material


class LocationMaterial(Material):
    id: int
    name: str | None = None
    kind: str | None = None


class LocationTextMaterial(LocationMaterial):
    text: str
    environment: str | None = None


class LocationLine(LocationTextMaterial):
    # その時刻の年までに起きた来歴(古い順。`reading.location_at`)。先の時刻の行と、年の決まっていない行は入らない
    histories: list[LocationHistoryRow]
