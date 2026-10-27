from pydantic import ConfigDict

from data_access_logic.knowers import KnowerRow
from data_access_logic.material import Form, Material, Timestamp


class IdeaHistoryRow(Form):
    """アイデアの子の行(idea_id は持たない)。入口の引数とレスポンスの両方に使う。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    # 読み出しで入る。配列で渡すときは、入れれば今ある行をその id で指し、空なら新しい行か、効く場所と始まりで当てる行
    id: int | None = None
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
    origin: str = "user"
    name: str
    kind: str
    parent_idea_id: int | None = None
    histories: list[IdeaHistoryRow]
    text: str


class IdeaName(Material):
    id: int
    name: str
    kind: str
