from pydantic import ConfigDict

from data_access_logic.knowers import KnowerRow
from data_access_logic.material import Form, Material, Timestamp


class IdeaRecognitionRow(Form):
    """アイデアの子の行(id と idea_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    name: str
    detail: str | None = None


class IdeaHistoryRow(Form):
    """アイデアの来歴の行(id と idea_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    # 起きた年。空なら年が決まっていない
    start: int | None = None
    description: str
    # 知る相手。渡さなければ、新しい行は誰も知らない、今ある行はそのまま(`db/child_lists.py` の `replaced_histories`)
    knowers: list[KnowerRow] | None = None


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
    histories: list[IdeaHistoryRow]
    # 本文(`text`)を知る相手
    knowers: list[KnowerRow]
    text: str


class IdeaName(Material):
    id: int
    name: str
    kind: str
