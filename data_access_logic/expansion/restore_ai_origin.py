#!/usr/bin/env python3
"""展開が足した行のうち、出自が作者(user)になった行を AI の行(ai)に戻す。

作者の書き手が AI の行を直すと、守り(`db/guard.py`)は行を作者の行にする。並べ替え・時刻の移しのような直しでも作者の行になるので、
中身は AI が書いたままの行を、作者が見分けられるよう AI の行に戻すときに使う。
戻すのは、展開の記録(`expansion_change`)に足したことの残る行だけ。展開の外で足した行は、誰が作ったか分からないので戻さない。

    RestoreAiOrigin(table_name="event", row_ids=[32, 33]).show()
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.expansion.record import RestoredAiOrigin
from data_access_logic.expansion.rows import model_of
from db.schema import ChangeOp, ExpansionChange, Origin, OriginMixin
from db.writer import restoring


class RestoreAiOrigin(CommitEntrypoint):
    def __init__(self, table_name: str, row_ids: list[int]):
        self.table_name = table_name
        self.row_ids = row_ids

    def execute(self, s: Session) -> RestoredAiOrigin:
        model = model_of(self.table_name)
        if not issubclass(model, OriginMixin):
            raise ValueError(f"{self.table_name} は出自を持たない表")
        added = set(s.scalars(select(ExpansionChange.row_id).where(
            ExpansionChange.table_name == self.table_name, ExpansionChange.op == ChangeOp.ADD,
            ExpansionChange.row_id.in_(self.row_ids))))
        restored: list[int] = []
        skipped: list[str] = []
        # 出自は守りだけが決めるので、展開の取り消しと同じく控えた値を戻す書き方で書く(守りも記録も通らない)
        with restoring():
            for row_id in self.row_ids:
                row = s.get(model, row_id)
                if row is None:
                    skipped.append(f"id={row_id}: 行が無い")
                elif row_id not in added:
                    skipped.append(f"id={row_id}: 展開が足した記録が無い")
                elif row.origin == Origin.AI:
                    skipped.append(f"id={row_id}: もう AI の行")
                else:
                    row.origin = Origin.AI.value
                    restored.append(row_id)
            s.flush()
        return RestoredAiOrigin(table_name=self.table_name, restored=restored, skipped=skipped)
