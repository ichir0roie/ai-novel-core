"""子の行(来歴・呼び名・知る相手)を一つずつ足す入口の共通の形。

`UpdateCharacter` などは来歴の配列をまるごと置き換えるので、今ある行を読み直して渡す手間と、別の行を書き換えてしまう危うさがある。
世界の展開(人物モードは足すことしかしない)と、一行だけ足したい作業はこちらを使う。
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.knowers import KnowerRow
from db.schema import Base, Character, Location


class AppendedRow(BaseModel):
    table: str
    id: int


def appended(s: Session, row: Base) -> AppendedRow:
    s.flush()
    return AppendedRow(table=row.__tablename__, id=row.id)


def check_knowers(s: Session, knowers: list[KnowerRow] | None) -> None:
    for knower in knowers or []:
        CommitEntrypoint.check_exists(s, Character, knower.knower_id, "knowers.knower_id")
        CommitEntrypoint.check_exists(s, Location, knower.location_id, "knowers.location_id")
