from data_access_logic.material import Material


class OracleRecord(Material):
    id: int
    origin: str = "user"
    title: str | None = None
    text: str


class MemeSourceCommitted(Material):
    """確定した行と、そのあと足したミームの件数。"""

    record: OracleRecord
    memes_added: int
