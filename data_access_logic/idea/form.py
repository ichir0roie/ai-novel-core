from typing import Annotated

from pydantic import Field

from data_access_logic.idea.record import IdeaHistoryRow, IdeaRecognitionRow
from data_access_logic.material import Form, References, Timestamp
from db.schema import Visibility


class IdeaCreateForm(Form):
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    text: str = ""
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    # 渡さなければ、kind の分類アイデアを場所から探して親にする
    parent_idea_id: int | None = None
    meme_seeded: bool = False
    recognitions: list[IdeaRecognitionRow] = []
    histories: list[IdeaHistoryRow] = []
    visibility: Visibility = Visibility.PUBLIC
    knower_ids: Annotated[list[int] | None, References("character")] = Field(
        default=None, title="知る人", description="本文が非公開(visibility=private)のとき、本文を知る人物")


class IdeaUpdateForm(Form):
    id: int
    name: str | None = None
    kind: str | None = None
    text: str | None = None
    location_id: int | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    parent_idea_id: int | None = None
    meme_seeded: bool | None = None
    # 渡すと配列をまるごと置き換える
    recognitions: list[IdeaRecognitionRow] | None = None
    histories: list[IdeaHistoryRow] | None = None
    visibility: Visibility | None = None
    # 渡すとまるごと置き換える
    knower_ids: Annotated[list[int] | None, References("character")] = Field(
        default=None, title="知る人", description="本文が非公開(visibility=private)のとき、本文を知る人物")
