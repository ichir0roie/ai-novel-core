from data_access_logic.material import Material


class OracleRecord(Material):
    id: int
    title: str | None = None
    meme_seeded: bool
    text: str
