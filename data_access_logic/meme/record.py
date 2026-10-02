from data_access_logic.material import Material


class MemeRecord(Material):
    id: int
    category: str | None = None
    text: str
