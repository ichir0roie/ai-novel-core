"""本文・来歴を知る相手の行(`db/schema.py` の `KnowerMixin`)。入口の引数とレスポンスの両方に使う。"""
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import ConfigDict, model_validator
from sqlalchemy.orm import Session

from data_access_logic.material import Form, Material, Named, References, Timestamp
from db.schema import Character, KnowerMixin, Location
from db.stamp import Stamp


class KnowerRow(Form):
    """知る人物か知る場所のどちらか一方を持つ(id と知られる側への外部キーは持たない。行は配列の並びで決まる)。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    knower_id: Annotated[int | None, References("character")] = None
    # その時刻にこの場所(配下も含む)に住む人物が知る
    location_id: Annotated[int | None, References("location")] = None
    # 知った時刻。空なら、知る人物の生まれ(場所なら、知られる行の始まりか場所のできた時刻)が入る
    start: Timestamp | None = None

    @model_validator(mode="after")
    def _one_knower(self) -> "KnowerRow":
        if (self.knower_id is None) == (self.location_id is None):
            raise ValueError("知る相手は knower_id か location_id のどちらか一方を渡す")
        return self


class KnowerMaterial(Material):
    """知る相手を名前で持つ。語り部と本文を書く Claude の材料に、誰が知っているかを添える。"""

    knower: Named | None = None
    location: Named | None = None
    start: Timestamp | None = None


def knowers_at(s: Session, knowers: Sequence[KnowerMixin], time: Stamp) -> list[KnowerMaterial]:
    """その時刻までに知った相手。先に知る相手を書き足しても、それより前の話には出ない。

    知る人物は知られる人物自身のことが多く、リレーションで読むと populate_existing で読み直した人物の子の行が
    読んでいないことに戻るので、`s.get` で引く。"""
    return [KnowerMaterial(knower=None if knower.knower_id is None else s.get_one(Character, knower.knower_id),
                           location=None if knower.location_id is None else s.get_one(Location, knower.location_id),
                           start=knower.start)
            for knower in knowers if knower.start is None or knower.start <= time]


def knowers_for_prompt(knowers: list[KnowerMaterial]) -> list[dict[str, Any]]:
    return [{"人物": None if knower.knower is None else knower.knower.name,
             "場所": None if knower.location is None else knower.location.name,
             "知った時刻": None if knower.start is None else str(knower.start)}
            for knower in knowers]
