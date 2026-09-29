from data_access_logic.material import Material


class LocationMaterial(Material):
    id: int
    name: str
    kind: str | None = None
