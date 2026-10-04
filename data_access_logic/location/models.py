from data_access_logic.material import Material


class LocationMaterial(Material):
    id: int
    name: str | None = None
    kind: str | None = None


class LocationTextMaterial(LocationMaterial):
    text: str
    environment: str | None = None
