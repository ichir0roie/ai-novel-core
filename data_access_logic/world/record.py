from pydantic import BaseModel


class RowRef(BaseModel):
    """行を表の名前と id と呼び名で指す。出自(user / ai)を添える(AI は user の行を直せない)。"""

    table: str
    id: int
    label: str
    origin: str | None = None


class LinkedRow(RowRef):
    # 当たった行とどう関わるか(関係・当事者・場所・親など)
    via: str


class WorldHit(RowRef):
    # 当たった語
    words: list[str]
    # 語の出た所の抜き書き
    excerpts: list[str]
    # 一段広げた関わる行
    linked: list[LinkedRow] = []


class WorldHits(BaseModel):
    hits: list[WorldHit]
