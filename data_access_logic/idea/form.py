from pydantic import Field

from data_access_logic.idea.record import IdeaRecognitionRow
from data_access_logic.material import Form, Timestamp


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
