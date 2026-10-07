from data_access_logic.material import Material


class MemeRecord(Material):
    id: int
    category: str | None = None
    anti_meme_id: int | None = None
    text: str
