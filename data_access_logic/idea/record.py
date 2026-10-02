from pydantic import ConfigDict

from data_access_logic.material import Form, Material, Timestamp


class IdeaRecognitionRow(Form):
    """アイデアの子の行(id と idea_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    name: str
    detail: str | None = None


class IdeaRecord(Material):
    id: int
    name: str
    kind: str
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    parent_idea_id: int | None = None
    meme_seeded: bool
    recognitions: list[IdeaRecognitionRow]
    text: str


class IdeaName(Material):
    id: int
    name: str
    kind: str
