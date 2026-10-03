"""本文・来歴を知る相手の行(`db/schema.py` の `KnowerMixin`)。入口の引数とレスポンスの両方に使う。"""
from typing import Annotated

from pydantic import ConfigDict, model_validator

from data_access_logic.material import Form, References, Timestamp


class KnowerRow(Form):
    """知る人物か知る場所のどちらか一方を持つ(id と知られる側への外部キーは持たない。行は配列の並びで決まる)。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    knower_id: Annotated[int | None, References("character")] = None
    # その時刻にこの場所(配下も含む)に住む人物が知る
    location_id: Annotated[int | None, References("location")] = None
    # 知った時刻。空なら初めから知っている
    start: Timestamp | None = None

    @model_validator(mode="after")
    def _one_knower(self) -> "KnowerRow":
        if (self.knower_id is None) == (self.location_id is None):
            raise ValueError("知る相手は knower_id か location_id のどちらか一方を渡す")
        return self
