from typing import Literal

from pydantic import Field

from data_access_logic.material import Form, Timestamp
from db.schema import ExpansionMode


class ExpansionCreateForm(Form):
    mode: ExpansionMode
    # 作者の一言(作者モード)か、人物の狙い(人物モード)
    prompt: str = ""
    story_id: int | None = None
    actor_id: int | None = None
    time: Timestamp | None = None
    location_id: int | None = None


class ExpansionFinishForm(Form):
    id: int
    # 何を足し・直したかの要約
    summary: str = ""
    status: Literal["done", "failed"] = "done"


class ConflictCreateForm(Form):
    expansion_id: int
    # 食い違う作者の行
    table_name: str
    row_id: int
    detail: str = Field(min_length=1)
    # こう直せば合う、という案
    proposal: str = ""


class ConflictResolveForm(Form):
    id: int
    status: Literal["accepted", "dismissed"]
