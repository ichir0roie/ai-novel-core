from pydantic import ConfigDict

from data_access_logic.knowers import KnowerRow
from data_access_logic.material import Form, Material, Timestamp


class IdeaHistoryRow(Form):
    """アイデアの子の行(id と idea_id は持たない。行は配列の並びで決まる)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    name: str
    detail: str | None = None
    # 知る相手。この相手だけが履歴を知る(効く場所・期間に住んでいても、入れなければ知らない)。渡さなければ、新しい行は行の無いまま、今ある行はそのまま
    # (`db/child_lists.py` の `replaced_histories`)
    knowers: list[KnowerRow] | None = None


class IdeaRecord(Material):
    id: int
    name: str
    kind: str
    start: Timestamp | None = None
    end: Timestamp | None = None
    parent_idea_id: int | None = None
    histories: list[IdeaHistoryRow]
    text: str


class IdeaName(Material):
    id: int
    name: str
    kind: str
