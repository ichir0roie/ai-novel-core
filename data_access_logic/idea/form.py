from typing import Annotated

from pydantic import Field

from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.knowers import KnowerRow
from data_access_logic.material import Form, References, Timestamp


class IdeaCreateForm(Form):
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    text: str = ""
    # 渡さなければ、kind の分類アイデアを履歴の行の場所から探して親にする
    parent_idea_id: int | None = None
    # 効く場所・時期はこの行で持つ。始まり(`start`)の空いた行しか無いと、時期未定として時刻のある引き方から外れる
    histories: list[IdeaHistoryRow] = []


class IdeaUpdateForm(Form):
    id: int
    name: str | None = None
    kind: str | None = None
    text: str | None = None
    parent_idea_id: int | None = None
    # 渡すと配列をまるごと置き換える
    histories: list[IdeaHistoryRow] | None = None


class IdeaHistoryChange(Form):
    """アイデアの履歴(呼び名)の行一つの直し。渡した欄だけを直す(空にする欄は null を渡す)。"""

    location_id: Annotated[int | None, References("location")] = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    # 渡すなら空にできない
    name: str = Field(default=None, min_length=1)
    detail: str | None = None
    # 渡せば知る相手をまるごと置き換える
    knowers: list[KnowerRow] | None = None
