from data_access_logic.material import Material, Timestamp


class LocationRecord(Material):
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
    text: str


class DeletedLocation(Material):
    id: int
    name: str | None = None
    kind: str | None = None
