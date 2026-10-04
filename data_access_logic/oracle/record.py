from data_access_logic.material import Material


class OracleRecord(Material):
    id: int
    title: str | None = None
    meme_seeded: bool
    text: str


class MemeSourceCommitted(Material):
    """確定した行と、そのあと足したミームの件数。"""

    record: OracleRecord
    memes_added: int
