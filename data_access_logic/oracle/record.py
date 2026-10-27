from data_access_logic.material import Material


class OracleRecord(Material):
    id: int
    origin: str = "user"
    title: str | None = None
    text: str
